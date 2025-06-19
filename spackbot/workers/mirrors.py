# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import boto3
import re
import sh

from datetime import datetime

import spackbot.helpers as helpers

from spackbot.queue import get_current_job

async def copy_pr_mirror(pr_mirror_url, shared_pr_mirror_url):
    """Copy between the S3 per-pr mirror and the shared pr mirror.

    Parameters:
        pr_mirror_url        (string): URL to S3 mirror for a PR
        shared_pr_mirror_url (string): URL to S3 mirror for shared PR binaries
    """
    pr_url = helpers.s3_parse_url(pr_mirror_url)
    shared_pr_url = helpers.s3_parse_url(shared_pr_mirror_url)

    s3 = boto3.resource("s3")
    pr_bucket_name = pr_url.get("bucket")
    pr_bucket = s3.Bucket(pr_bucket_name)
    pr_mirror_prefix = pr_url.get("prefix")

    shared_pr_bucket = s3.Bucket(shared_pr_url.get("bucket"))
    shared_pr_mirror_prefix = shared_pr_url.get("prefix")

    # Files extensions to copy
    extensions = (".spack", ".spec.json", ".spec.yaml", ".spec.json.sig")

    for obj in pr_bucket.objects.filter(Prefix=pr_mirror_prefix):
        if obj.key.endswith(extensions):
            # Create a new opject replacing the first instance of the pr_mirror_prefix
            # with the shared_pr_mirror_prefix.
            new_obj = shared_pr_bucket.Object(
                obj.key.replace(pr_mirror_prefix, shared_pr_mirror_prefix, 1)
            )
            # Copy the PR mirror object to the new object in the shared PR mirror
            new_obj.copy(
                {
                    "Bucket": pr_bucket_name,
                    "Key": obj.key,
                }
            )


async def delete_pr_mirror(pr_mirror_url):
    """Delete a mirror from S3. This routine was written for PR mirrors
    but is general enough to be used to delete any S3 mirror.

        Parameters:
            pr_mirror_url (string): URL to S3 mirror
    """
    pr_url = helpers.s3_parse_url(pr_mirror_url)

    s3 = boto3.resource("s3")
    pr_bucket = s3.Bucket(pr_url.get("bucket"))
    pr_mirror_prefix = pr_url.get("prefix")
    pr_bucket.objects.filter(Prefix=pr_mirror_prefix).delete()


def list_ci_stacks(spack_root):
    """Loop through the CI stacks in the spack repo.

    Parameters:
        spack_root (path): Root of a spack clone
    """
    pipeline_root = f"{spack_root}/share/spack/gitlab/cloud_pipelines/stacks/"
    for stack in os.listdir(pipeline_root):
        if os.path.isfile(f"{pipeline_root}/{stack}/spack.yaml"):
            yield stack


def hash_from_key(key):
    """This works because we guarentee the hash is in the key string.
    If this assumption is ever broken, this code will break.

        Parameters:
            key (string): File/Object name that contains a spack package concrete
                          hash.
    """
    h = None
    # hash is 32 chars long between a "-" and a "."
    # examples include:
    # linux-ubuntu18.04-x86_64-gcc-8.4.0-armadillo-10.5.0-gq3ijjrtnzgpm4bvuamjr6wa7hzxkypz.spack
    # linux-ubuntu18.04-x86_64-gcc-8.4.0-armadillo-10.5.0-gq3ijjrtnzgpm4bvuamjr6wa7hzxkypz.spec.json
    h = re.findall(r"-([a-zA-Z0-9]{32,32})\.", key.lower())
    if len(h) > 1:
        # Error, multiple matches are ambigious
        h = None
    elif h:
        h = h[0]
    return h


def check_skip_job(job=None):
    """Check if there is another job in the queue that is of the same type.

    Parameters:
        job (rq.Job): Job to check (default=rq.get_current_job)
    """

    if not job:
        job = get_current_job()

    job_type = job.meta.get("type", "-")
    skip = False
    logger.debug(f"-- Checking skip job({job.id}): {job_type}")
    # Check if another job of this type is queued
    queue = get_queue(job.origin)
    for _job in queue.jobs:
        _job_type = _job.meta["type"]
        logger.debug(f"-- job({_job.id}): {_job_type}")
        if _job.meta["type"] == job_type:
            skip = True
            break

    if skip:
        logger.debug(f"Skipping {job_type} job")
        pr_number = job.meta.get("pr_number", None)
        if pr_number:
            logger.debug(f"PR: https://github.com/spack/spack/pull/{pr_number}")

    return skip


# Prune per stack mirror
async def prune_mirror_duplicates(shared_pr_mirror_url, publish_mirror_url):
    """Prune objects from the S3 mirror for shared PR binaries that have been published to the
    develop mirror or have expired.

        Parameters:
            shared_pr_mirror_url (string): URL to S3 mirror for shared PR binaries
            publish_mirror_url   (string): URL to S3 mirror for published PR binaries
    """

    # Current job stack
    if check_skip_job():
        return

    s3 = boto3.resource("s3")

    with helpers.temp_dir() as cwd:
        git.clone(
            "--branch",
            helpers.pr_expected_base,
            "--depth",
            1,
            helpers.spack_upstream,
            "spack",
        )

        for stack in list_ci_stacks(f"{cwd}/spack"):
            shared_pr_url = helpers.s3_parse_url(
                shared_pr_mirror_url.format_map({"stack": stack})
            )
            shared_pr_bucket_name = shared_pr_url.get("bucket")
            shared_pr_bucket = s3.Bucket(shared_pr_bucket_name)
            shared_pr_mirror_prefix = shared_pr_url.get("prefix")

            publish_url = helpers.s3_parse_url(
                publish_mirror_url.format_map({"stack": stack})
            )
            publish_bucket = s3.Bucket(publish_url.get("bucket"))
            publish_mirror_prefix = publish_url.get("prefix")

            # All of the expected possible spec file extensions
            extensions = (".spec.json", ".spec.yaml", ".spec.json.sig")

            # Get the current time for age based pruning
            now = datetime.now()
            delete_specs = set()
            shared_pr_specs = set()
            for obj in shared_pr_bucket.objects.filter(
                Prefix=shared_pr_mirror_prefix,
            ):
                # Need to convert from aware to naive time to get delta
                last_modified = obj.last_modified.replace(tzinfo=None)
                # Prune obj.last_modified > helpers.shared_pr_mirror_retire_after_days
                # (default: 7) days to avoid storing cached objects that only
                # existed during development.
                # Anything older than the retirement age should just be indesciminately
                # pruned
                if (
                    now - last_modified
                ).days >= helpers.shared_pr_mirror_retire_after_days:
                    logger.debug(
                        f"pr mirror pruning {obj.key} from s3://{shared_pr_bucket_name}: "
                        "reason(age)"
                    )
                    obj.delete()

                    # Grab the hash from the object, to ensure all of the files associated with
                    # it are also removed.
                    spec_hash = hash_from_key(obj.key)
                    if spec_hash:
                        delete_specs.add(spec_hash)
                    continue

                if not obj.key.endswith(extensions):
                    continue

                # Get the hashes in the shared PR bucket.
                spec_hash = hash_from_key(obj.key)
                if spec_hash:
                    shared_pr_specs.add(spec_hash)
                else:
                    logger.error(
                        f"Encountered spec file without hash in name: {obj.key}"
                    )

            # Check in the published base branch bucket for duplicates to delete
            for obj in publish_bucket.objects.filter(
                Prefix=publish_mirror_prefix,
            ):
                if not obj.key.endswith(extensions):
                    continue

                spec_hash = hash_from_key(obj.key.lower())
                if spec_hash in shared_pr_specs:
                    delete_specs.add(spec_hash)

            # Also look at the .spack files for deletion
            extensions = (".spack", *extensions)

            # Delete all of the objects with marked hashes
            for obj in shared_pr_bucket.objects.filter(
                Prefix=shared_pr_mirror_prefix,
            ):
                if not obj.key.endswith(extensions):
                    continue

                if hash_from_key(obj.key) in delete_specs:
                    logger.debug(
                        f"pr mirror pruning {obj.key} from s3://{shared_pr_bucket_name}: "
                        "reason(published)"
                    )
                    obj.delete()


# Upate index per stack mirror
async def update_mirror_index(base_mirror_url):
    """Use spack buildcache command to update index for each Spack CI stack mirror.

    Parameters:
        base_mirror_url (string): Base URL to S3 mirror with the format placeholder {stack}
                             where the stack name will go in the URL.
    """

    # Current job stack
    if check_skip_job():
        return

    with helpers.temp_dir() as cwd:
        git.clone(
            "--branch",
            helpers.pr_expected_base,
            "--depth",
            1,
            helpers.spack_upstream,
            "spack",
        )
        spack = sh.Command(f"{cwd}/spack/bin/spack")

        for stack in list_ci_stacks(f"{cwd}/spack"):
            stack_mirror_url = base_mirror_url.format_map({"stack": stack})
            print(f"Updating binary index at {stack_mirror_url}")
            helpers.run_command(
                spack,
                [
                    "-d",
                    "buildcache",
                    "update-index",
                    f"{stack_mirror_url}",
                ],
            )

