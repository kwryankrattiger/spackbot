# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import subprocess

from sh.contrib import git
from typing import List

import spackbot.comments as comments
import spackbot.config as cfg
import spackbot.helpers as helpers

from spackbot.queue import get_current_job
from spackbot.auth import REQUESTER

logger = helpers.get_logger(__name__)

allow_edits_url = (
    "https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/"
    "allowing-changes-to-a-pull-request-branch-created-from-a-fork"
    "#enabling-repository-maintainer-permissions-on-existing-pull-requests"
)


def is_up_to_date(output):
    """
    A commit can fail if there are no changes!
    """
    return "nothing to commit" in output


def report_style_failure(job, connection, type, value, traceback):
    user_msg = comments.format_error_message(
        "I encountered an error attempting to format style.", type, value, traceback
    )
    post_failure_message(job, user_msg)


async def fix_style(git_url: str, branch: str, user: str, email: str, files: List[str], style: cfg.Style):
    with helpers.temp_dir() as cwd:
        # Clone the repo
        git.clone(git_url, "fix-style")
        os.chdir("fix-style")

        # Configure the user
        git.config("user.name", user)
        git.config("user.email", email)

        git.fetch("origin", f"{branch}:fix_style")
        git.checkout("fix_style")

        style_output = ""
        for command in style.tools:
            output = ""
            error = ""
            if style.strategy == Style.Strategy.BATCH:
                logger.debug("[command]")
                logger.debug(f"{command}")
                res = subprocess.run(command)
                output = res.stdout
                error = res.stderr
            elif style.strategy == Style.Strategy.FILE:
                for file in files:
                    cmd = command.format(file=file)
                    logger.debug("[command]")
                    logger.debug(f"{cmd}")
                    res = subprocess.run(cmd)
                    output += res.stdout
                    error += res.stderr

            logger.debug("[output]")
            logger.debug(output)
            logger.debug("[error]")
            logger.debug(error)

            style_output += output

        message = comments.get_style_message(style_output)

        # Only re-add listed files
        for file in files:
            git.add(file)

        commit_output = git.commit(
            "-m",
            f"[{helpers.botname}] updating style on behalf of @{user}"
        )

        if is_up_to_date(commit_output):
            logger.info("Unable to make any further changes")
            message += "\nI wasn't able to make any further changes, but please see the message above for remaining issues you can fix locally!"
            return message

        try:
            git.push(
                "origin",
                f"fix_style:{branch}",
                _ok_code=[0]
            )
            message += "\n\nI've updated the branch with style fixes."
        except ErrorReturnCode as inst:
            logger.error(f"Unable to push to branch {git_url}:{branch}")
            message += (
                    f"\n\nIt looks like I'm not able to push to your branch. 😭️"
                    f" Did you check [Allow edits from maintainers]({allow_edits_url})"
                    f" when you opened the PR?"
                )

        return message


async def fix_style_task(event, config):
    """
    We first retrieve metadata about the pull request. If the request comes
    from anyone with write access to the repository, we commit, and we commit
    under the identity of the original person that opened the PR.
    """
    job = get_current_job()
    token = job.meta["token"]

    async with aiohttp.ClientSession() as session:
        gh = gh_aiohttp.GitHubAPI(session, REQUESTER, oauth_token=token)

        pr_url = event.data["issue"]["pull_request"]["url"]

        pr = await gh.getitem(pr_url)

        logger.debug("GitHub PR")
        logger.debug(pr)

        # Get the sender of the PR - do they have write?
        sender = event.data["sender"]["login"]
        repository = event.data["repository"]
        collaborators_url = repository["collaborators_url"]
        author = pr["user"]["login"]

        logger.debug(
            f"sender = {sender}, repo = {repository}, collabs_url = {collaborators_url}"
        )

        # If they didn't create the PR and don't have write, we don't allow the command
        if sender != author and not await helpers.found(
            gh.getitem(collaborators_url, {"collaborator": sender})
        ):
            msg = f"Sorry {sender}, I cannot do that for you. Only {author} and users with write can make this request!"
            await gh.post(event.data["issue"]["comments_url"], {}, data={"body": msg})
            return

        # Tell the user the style fix is going to take a minute or two
        message = "Let me see if I can fix that for you!"
        await gh.post(event.data["issue"]["comments_url"], {}, data={"body": message})

        # Get the username of the original committer
        user = pr["user"]["login"]

        # We need the user id if the user is before July 18, 2017.  See note about why
        # here:
        #
        #     https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email-address
        #
        email = await helpers.get_user_email(gh, user)

        # We need to use the git url with ssh
        remote_branch = pr["head"]["ref"]
        local_branch = "spackbot-style-check-working-branch"
        full_name = pr["head"]["repo"]["full_name"]
        fork_url = f"git@github.com:{full_name}.git"

        logger.info(
            f"fix_style_task, user = {user}, email = {email}, fork = {fork_url}, branch = {remote_branch}\n"
        )

        message = await fix_style(
            fork_url,
            remote_branch,
            user,
            email,
            config.tools
        )

        await gh.post(
            event.data["issue"]["comments_url"], {}, data={"body": message}
        )
