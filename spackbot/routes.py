# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import re

from gidgethub import sansio

# View handler functions
import spackbot.handlers as handlers
import spackbot.comments as comments
import spackbot.helpers as helpers
import spackbot.workers as workers

from gidgethub import routing
from typing import Any

logger = helpers.get_logger(__name__)


class SpackbotRouter(routing.Router):
    """
    Custom router to handle common interactions for spackbot
    """

    async def dispatch(self, event: sansio.Event, *args: Any, **kwargs: Any) -> None:
        """Dispatch an event to all registered function(s)."""

        # if we haven't retrieved package list yet, do so
        if not hasattr(self, "packages"):
            self.packages = await helpers.list_packages()

        # for all endpoints, spackbot should not respond to himself!
        if "comment" in event.data and re.search(
            helpers.alias_regex, event.data["comment"]["user"]["login"]
        ):
            return

        found_callbacks = self.fetch(event)
        for callback in found_callbacks:
            await callback(event, *args, **kwargs)


router = SpackbotRouter()


@router.register("check_run", action="completed")
async def add_style_comments(event, gh, *args, session, **kwargs):
    """
    Respond to all check runs (e.g., for style or GitHub Actions)
    """
    # Nothing to do with success
    if event.data["check_run"]["conclusion"] == "success":
        return

    check_name = event.data["check_run"]["name"]
    logger.info(f"check run {check_name} unsuccesful")

    config = cfg.from_event(event)
    if not config.has_feature("style"):
        return

    # If it's not a style check, we don't care
    if check_name == "style":
        await handlers.style_comment(event, gh)


@router.register("pull_request", action="opened")
async def on_pull_request(event, gh, *args, session, **kwargs):
    """
    Respond to the pull request being opened
    """
    config = cfg.from_event(event)
    if config.has_feature("maintainers"):
        await handlers.add_reviewers(event, gh)


@router.register("issue_comment", action="created")
async def add_comments(event, gh, *args, session, **kwargs):
    """
    Receive pull request comments
    """
    # We can only tell PR and issue comments apart by this field
    if "pull_request" not in event.data["issue"]:
        return

    # Respond with appropriate messages
    comment = event.data["comment"]["body"]

    # Parse the comment string to extract the command and arguments
    m = re.match(f"{helpers.botname} ?(.*)", comment)
    if not m:
        return

    handler_args = m.groups()[0].lower().split()

    # If no args, send help
    if not handler_args:
        handler_args.append("help")

    message = None

    config = cfg.from_event(event)
    # @spackbot commands OR @spackbot help
    if any(opt in handler_args for opt in ("commands", "help")):
        logger.debug("Responding to request for help commands.")
        message = comments.commands_message

    # @spackbot hello
    elif handler_args[0] == "hello":
        logger.info(f"Responding to hello message {comment}...")
        message = comments.say_hello()

    # Hey @spackbot tell me a joke!
    elif handler_args[0] == "joke":
        logger.info(f"Responding to request for joke {comment}...")
        message = await comments.tell_joke(gh)

    elif any(opt in handler_args for opt in ("style", "fix")):
        if not config.has_feature("style"):
            return
        logger.debug("Responding to request to fix style")
        message = await handlers.fix_style(event, gh, *args, **kwargs)

    # @spackbot maintainers or @spackbot request review
    elif any(opt in handler_args for opt in ("maintainers", "request", "review")):
        if not config.has_feature("maintainers"):
            return
        logger.debug("Responding to request to assign maintainers for review.")
        await handlers.add_reviewers(event, gh)

    # @spackbot run pipeline | @spackbot re-run pipeline
    elif any(opt in handler_args for opt in ("rerun", "re-run", "run")) and "pipeline" in handler_args:
        if not config.has_feature("pipelines"):
            return
        logger.info("Responding to request to re-run pipeline...")
        await handlers.run_pipeline(event, gh, **kwargs)

    # @spackbot rebuild everything
    elif all(opt in handler_args for opt in ("rebuild", "everything")):
        if not config.has_feature("pipelines"):
            return
        logger.info("Responding to request to rebuild everthing...")
        await handlers.run_pipeline_rebuild_all(event, gh, **kwargs)

    if message:
        await gh.post(event.data["issue"]["comments_url"], {}, data={"body": message})


@router.register("pull_request", action="opened")
@router.register("pull_request", action="synchronize")
async def label_pull_requests(event, gh, *args, session, **kwargs):
    """
    Add labels to PRs based on which files were modified.
    """
    config = cfg.from_event(event)
    if config.has_feature("label"):
        await handlers.add_labels(event, gh, config.label)


@router.register("pull_request", action="closed")
async def on_closed_pull_request(event, gh, *args, session, **kwargs):
    """
    Respond to the pull request closed
    """
    config = cfg.from_event(event)
    if config.has_feature("pipelines"):
        return

    await workers.close_pr_gitlab_branch(event, gh)

    # If there is mirror configured close it
    if config.pipelines.pr_mirror_base:
        await handlers.close_pr_mirror(event, gh)
