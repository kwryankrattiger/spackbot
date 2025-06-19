# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import urllib.parse

import aiohttp
from gidgethub import aiohttp as gh_aiohttp

import spackbot.comments as comments
import spackbot.helpers as helpers

from spackbot.auth import REQUESTER

# We can only make the pipeline request with a GITLAB TOKEN
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN")


async def close_pr_gitlab_branch(event, gh):
    pr_branch_name = helpers.pr_branch_from_event(event)

    url = helpers.gitlab_spack_project_url
    url = f"{url}/repository/branches/{pr_branch_name}"

    GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN")
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}

    await helpers.delete(url, headers=headers)


async def check_gitlab_has_latest(branch_name, pr_head_sha, gh, comments_url):
    """
    Given the name of the branch supposedly pushed to gitlab, check if it
    is the latest revision found on github.  If gitlab doesn't have the
    latest, the pipeline cannot be run, so post a comment on the PR to
    explain why, if that is the case.

    Arguments:
        branch_name (str): Name of branch to query on GitLab for latest commit
        pr_head_sha (str): SHA of PR head from GitHub
        gh: GitHubAPI object for posting comments on the PR
        comments_url (str): URL to post any error message to

    Returns: True if gitlab has the latest revsion, False otherwise.
    """
    # Get the commit for the PR branch from GitLab to see what's been pushed there
    headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
    commit_url = f"{helpers.gitlab_spack_project_url}/repository/commits/{branch_name}"
    gitlab_commit = await helpers.get(commit_url, headers)

    error_msg = comments.cannot_run_pipeline_comment

    if not gitlab_commit or "parent_ids" not in gitlab_commit:
        details = f"Unexpected response from gitlab: {gitlab_commit}"
        logger.debug(f"Problem with {branch_name}: {details}")
        msg = comments.format_generic_details_msg(error_msg, details)
        await gh.post(comments_url, {}, data={"body": msg})
        return False

    parent_ids = gitlab_commit["parent_ids"]

    if pr_head_sha not in parent_ids:
        pids = [pid[:7] for pid in parent_ids]
        details = f"pr head: {pr_head_sha[:7]}, gitlab commit parents: {pids}"
        logger.debug(f"Problem with {branch_name}: {details}")
        msg = comments.format_generic_details_msg(error_msg, details)
        await gh.post(comments_url, {}, data={"body": msg})
        return False

    return True


def post_failure_message(job, msg):
    """
    Get the api token from the job metadata, use it to post a comment on
    the PR containing the excepttion encountered and stack trace.

    """
    token = None
    if "token" in job.meta:
        token = job.meta["token"]

    url = job.meta["post_comments_url"]
    data = {"body": msg}

    helpers.synchronous_http_request(url, data=data, token=token)
    logger.error(msg)


def report_pipeline_failure(job, connection, type, value, traceback):
    user_msg = comments.format_error_message(
        "I encountered an error attempting to run the pipeline.",
        type,
        value,
        traceback,
    )
    post_failure_message(job, user_msg)


async def run_pipeline_task(event):
    """
    Send an api request to gitlab telling it to run a pipeline on the
    PR branch for the associated PR.  If the job metadata includes the
    "rebuild_everything" key set to True, then this method will take the
    extra couple steps to trigger a pipeline that will rebuild all specs
    from source.  This involves clearing the dedicated mirror for the
    associated PR, and setting the "SPACK_PRUNE_UNTOUCHED" env var to
    False (so that pipeline generation doesn't trim jobs for specs it
    thinks aren't touched by the PR).
    """
    job = get_current_job()
    token = job.meta["token"]
    rebuild_everything = job.meta.get("rebuild_everything")

    async with aiohttp.ClientSession() as session:
        gh = gh_aiohttp.GitHubAPI(session, REQUESTER, oauth_token=token)

        comments_url = event.data["issue"]["comments_url"]

        # Early exit if not authenticated
        if not GITLAB_TOKEN:
            msg = "I'm not able to run the pipeline now because I don't have authentication."
            await gh.post(comments_url, {}, data={"body": msg})
            return

        # Get the pull request number
        pr_url = event.data["issue"]["pull_request"]["url"]
        *_, number = pr_url.split("/")

        # We need the pull request branch
        pr = await gh.getitem(pr_url)

        # Get the sender of the PR - do they have write?
        sender = event.data["sender"]["login"]
        repository = event.data["repository"]
        collaborators_url = repository["collaborators_url"]
        author = pr["user"]["login"]

        # If it's the PR author, we allow it
        if author == sender:
            logger.info(
                f"Author {author} of PR #{number} is requesting a pipeline run."
            )

        # If they don't have write, we don't allow the command
        elif not await helpers.found(
            gh.getitem(collaborators_url, {"collaborator": sender})
        ):
            logger.info(f"Not found: {sender}")
            msg = f"Sorry {sender}, I cannot do that for you. Only users with write can make this request!"
            await gh.post(comments_url, {}, data={"body": msg})
            return

        # We need the branch name plus number to assemble the GitLab CI api requests
        branch = pr["head"]["ref"]
        pr_mirror_key = f"pr{number}_{branch}"
        branch = urllib.parse.quote_plus(pr_mirror_key)

        # If gitlab doesn't have the latest PR head sha from GitHub, we can't run the
        # pipeline.
        head_sha = pr["head"]["sha"]
        if not await check_gitlab_has_latest(branch, head_sha, gh, comments_url):
            return

        url = f"{helpers.gitlab_spack_project_url}/pipeline?ref={branch}"

        if rebuild_everything:
            # Rebuild everything is accomplished by telling spack pipeline generation
            # not to do any of the normal pruning (DAG pruning, untouched spec pruning).
            # But we also wipe out the contents of the PR-specific mirror.  See docs on
            # use of variables:
            #
            #    https://docs.gitlab.com/ee/api/index.html#array-of-hashes
            #
            # Also see issue contradicting the docs:
            #
            #    https://gitlab.com/gitlab-org/gitlab/-/issues/23394
            #
            url = (
                f"{url}&variables[][key]=SPACK_PRUNE_UNTOUCHED&variables[][value]=False"
            )
            url = f"{url}&variables[][key]=SPACK_PRUNE_UP_TO_DATE&variables[][value]=False"
            mirror_template = urllib.parse.quote_plus("single-src-pr-mirrors.yaml.in")
            url = f"{url}&variables[][key]=PIPELINE_MIRROR_TEMPLATE&variables[][value]={mirror_template}"

            logger.info(
                f"Deleting {helpers.pr_mirror_base_url}/{pr_mirror_key} for rebuild request by {sender}"
            )

            pr_url = helpers.s3_parse_url(
                f"{helpers.pr_mirror_base_url}/{pr_mirror_key}"
            )
            # Wipe out PR binary mirror contents
            s3 = boto3.resource("s3")
            bucket = s3.Bucket(pr_url.get("bucket"))
            bucket.objects.filter(Prefix=pr_url.get("prefix")).delete()

        # Use helpers.post because it creates a new session (and here we are
        # communicating with gitlab rather than github).
        headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
        logger.info(f"{sender} triggering pipeline, url = {url}")
        result = await helpers.post(url, headers)

        detailed_status = result.get("detailed_status", {})
        if "details_path" in detailed_status:
            url = urllib.parse.urljoin(
                helpers.spack_gitlab_url, detailed_status["details_path"]
            )
            logger.info(f"Triggering pipeline on {branch}: {url}")
            msg = f"I've started that [pipeline]({url}) for you!"
            await gh.post(comments_url, {}, data={"body": msg})
        else:
            logger.info(f"Problem triggering pipeline on {branch}")
            logger.info(result)
            msg = "I had a problem triggering the pipeline."
            await gh.post(comments_url, {}, data={"body": msg})
