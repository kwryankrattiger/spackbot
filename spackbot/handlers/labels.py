# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import re

import spackbot.helpers as helpers

logger = helpers.get_logger(__name__)

async def add_labels(event, gh):
    """
    Add labels to a pull request
    """
    pull_request = event.data["pull_request"]
    number = event.data["number"]
    logger.info(f"Labeling PR #{number}...")

    if not cfg.CONFIG.has_feature("label"):
        return

    label_patterns = cfg.from_event(event).get_label().label_patterns
    extra_attributes = cfg.from_event(event).get_label().extra_attributes

    # Iterate over modified files and create a list of labels
    # https://developer.github.com/v3/pulls/#list-pull-requests-files
    labels = set()
    async for file in gh.getiter(pull_request["url"] + "/files"):
        filename = file["filename"]
        status = file["status"]
        logger.info(f"Filename: {filename}")
        logger.info(f"Status: {status}")

        spackbot.actions.label.compute_file_attributes(file, extra_attributes)
        labels.update(spackbot.actions.label.collect_labels(file, label_mapping))

    logger.info(f"Adding the following labels: {labels}")

    # https://developer.github.com/v3/issues/labels/#add-labels-to-an-issue
    if labels:
        await gh.post(pull_request["issue_url"] + "/labels", data=list(labels))
