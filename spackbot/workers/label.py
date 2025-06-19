# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import re

from spackbot.helpers import get_logger

logger = get_logger(__name__)

def compute_file_attributes(file, attributes):
    """Compute custom file attributes from existing file attributes

    Args:
        file:
            file object from Github
            (ref. https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28#list-pull-requests-files)

        attributes:
            config section defining custom attributes

    Note:
        Custom attributes may be computed from other computed attributes, however unresolved attributes are skipped.
    """
    unresolved_attrs = attributes
    while unresolved_attrs:
        do_retry = False
        retry_attrs = {}
        for attr in unresolved_attrs:
            if attr in file:
                logger.warn(f"skipping attribute {attr}, already exists")
                continue

            from_attr = attributes[attr]["from"]
            from_attr = file.get(from_attr)
            if from_attr:
                print(f"from: {from_attr}")
                print(f"match: {attributes[attr]['match']}")
                m = re.match(attributes[attr]["match"], from_attr)
                # Get the match group id, default is first match group
                group_id = attributes[attr].get("group", 0)
                match_groups = m.groups() if m else ()
                print(f"group: {group_id}, in {match_groups}")
                if group_id >= len(match_groups):
                    logger.debug(f"skipping attribute {attr}, no match found")
                    file[attr] = ""
                    continue
                file[attr] = match_groups[group_id]
                # Retry resolving attributes with new attributes
                do_retry = True
            else:
                retry_attrs[attr] = attributes[attr]

        if do_retry:
            # Something new was computed, so retry
            unresolved_attrs = retry_attrs
        else:
            # Skip all of the remaining unresolved attributes
            for attr in retry_attrs:
                logger.debug(f"skipping attribute {attr}, could not compute 'from' attribute {attributes[attr]['from']}")
                file[attr] = ""
            unresolved_attrs = None


def collect_labels(file, label_patterns):
    labels = []
    # If the file's attributes match any patterns in label_patterns, add
    # the corresponding labels.
    for label, pattern_dict in label_patterns.items():
        attr_matches = []
        # Pattern matches for for each attribute are or'd together
        for attr, patterns in pattern_dict.items():
            # 'patch' is an example of an attribute that is not required to
            # appear in response when listing pull request files.  See here:
            #
            #    https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files
            #
            # If we don't get some attribute in the response, no labels that
            # depend on finding a match in that attribute should be added.
            attr_matches.append(
                any(p.search(file[attr]) for p in patterns)
                if attr in file
                else False
            )
        # If all attributes have at least one pattern match, we add the label
        if all(attr_matches):
            labels.append(label)

    return labels


async def add_labels(event, gh, config):
    """
    Add labels to a pull request
    """
    pull_request = event.data["pull_request"]
    number = event.data["number"]
    logger.info(f"Labeling PR #{number}...")

    label_patterns = config.label_patterns
    extra_attributes = config.extra_attributes

    # Iterate over modified files and create a list of labels
    # https://developer.github.com/v3/pulls/#list-pull-requests-files
    labels = set()
    async for file in gh.getiter(pull_request["url"] + "/files"):
        filename = file["filename"]
        status = file["status"]
        logger.info(f"Filename: {filename}")
        logger.info(f"Status: {status}")

        compute_file_attributes(file, extra_attributes)
        labels.update(collect_labels(file, label_mapping))

    logger.info(f"Adding the following labels: {labels}")

    # https://developer.github.com/v3/issues/labels/#add-labels-to-an-issue
    if labels:
        await gh.post(pull_request["issue_url"] + "/labels", data=list(labels))
