# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

"""Load the configuration file for spackbot
"""

import os
import yaml
import enum

from typing import Any, Dict, List, Optional

from spackbot.helpers import Singleton, get_logger

logger = get_logger(__name__)

class Style:
    class Strategy(enum.Enum):
        BATCH = enum.auto()
        FILE = enum.auto()

    def __init__(self, data):
        if isinstance(data["tools"], str):
            tool = data["tools"]
            data["tools"] = [tool]

        if "strategy" not in data:
            data["strategy"] = Style.Strategy.BATCH

        self.__dict__.update(data)

class Label:
   """Label configs

   Members:
        label_patterns: maps labels to patterns that tell us to apply the labels.

            Entries in the dict are of the form:
            {
                "label": {
                    "attr1": [r"regex1.1", r"regex1.2"],
                    "attr2": [r"regex2.1", r"regex2.2", r"regex2.3"],
                    "attr3": r"regex3.1",
                    ...
                },
                ...
            }

            attr1, attr2, etc. are attributes on files in the PR (e.g., status,
            filename, etc).  If all attrs for a label have at least one regex match,
            then that label will be added to the PR.

        extra_attributes: a way to generate custom attributes from existing file attributes.
            Entries in the dict are of the form:
            {
                "attr2": {
                    "from": "attr1"
                    "match": "regex",
                    "group_id": 0
                },
                ...
            }

            attr2 is computed from attr1 by extracting the matched grouping at group_id.
    """

    def __init__(self, data):
        label_pattern = data.get("mapping", {})
        extra_attributes = data.get("extra-attributes", {})

        # pre-compile all the regexes above, and ensure that all pattern dict values are lists
        for label, pattern_dict in label_patterns.items():
            for attr in pattern_dict.keys():
                patterns = pattern_dict[attr]
                if not isinstance(patterns, list):
                    patterns = [patterns]
                pattern_dict[attr] = [re.compile(s) for s in patterns]

        for attr, rules in extra_attributes.items():
            if "from" not in rules:
                logger.error(f"missing 'from' in extra_attribute {attr}")
            if "match" not in rules:
                logger.error(f"missing 'match' in extra_attribute {attr}")

class SpackbotConfig:
    def __init__(self, data: dict):
        supported_keys = {
            "style":     # configuration on how to check and fix style for PR
                ["tools"],
            "pipeline":  # Enable gitlab pipeline management
                ["gitlab", "actions"],
            "label":     # Label mapping to status/regex
                ["mapping", "extra-attributes"],
            "maintainers":      # ping maintainers based on patch and/or package info
                ["git", "packages"],
            "jokes": []
        }


        bad_keys = {}
        for key in data:
            if key not in supported_keys:
                keys = bad_keys.get("_", [])
                keys.append(key)
                bad_keys["_"] = keys
            else:
                if not isinstance(data[key], dict):
                    continue

                for option in data[key]:
                    if option not in supported_keys[key]:
                        keys = bad_keys.get(option, [])
                        keys.append(key)
                        bad_keys[option] = keys

        if bad_keys:
            message = ""
            for level, keys in bad_keys.items():
                if not level == "_":
                    message += f"{level}:["
                message += ", ".join(keys)
                if not level == "_":
                    message += f"], "
            raise RuntimeError(f"Dectected unrecognized keys: {message}")

        self.__dict__.update(data)
        self._labels_compiled = False

    def get_config(self, feature) -> Dict[str,Any]:
        return getattr(self, feature, {})

    def has_feature(self, feature):
        return feature in self.__dict__

    def get_style(self) -> Optional[Style]:
        conf = self.get_config("style")
        if conf:
            return Style(conf)
        else:
            return None

    def get_label(self) -> Optional[Label]:
        conf = self.get_config("label")
        if conf:
            return label(conf)
        else:
            return None

    def _compile_label_patterns(self):
        """Compile regex match strings once"""
        if self._labels_compiled:
            return

        self._labels_compiled = True

        label_pattern = self.get_config("label").get("mapping")
        if label_pattern:
            for label, pattern_dict in label_patterns.items():
                for attr in pattern_dict.keys():
                    patterns = pattern_dict[attr]
                    if not isinstance(patterns, list):
                        patterns = [patterns]
                    pattern_dict[attr] = [re.compile(s) for s in patterns]

        attr_pattern = self.get_config("label").get("extra_attributes")
        if attr_pattern:
            for attr in attr_pattern.keys():
                pattern = attr_pattern[attr]
                attr_pattern[attr] = re.compile(pattern)

    def get_label_mappings() -> Optional[Dict[str, Any]]:
        if not self.has_feature("label"):
            return None

        self._compile_label_patterns()
        return self.get_config("label").get("mapping")

    def get_label_attributes() -> Optional[Dict[str, Any]]:
        if not self.has_feature("label"):
            return None

        self._compile_label_patterns()
        return self.get_config("label").get("extra_attributes")


def _load_config():
    configfile = os.environ.get("SPACKBOT_CONFIG_FILE", "/etc/spackbot/config.yaml")

    if not os.path.exists(configfile):
        raise RuntimeError(f"Missing config file: {configfile}")

    with open(configfile, "r") as fd:
        # TODO: use Loader
        data = yaml.load(fd, Loader=yaml.Loader)

    config_map = {}
    for url, config in data.items():
        assert isinstance(config, dict)
        config_map[url] = SpackbotConfig(config)
    return config_map

CONFIG: Dict[str, SpackbotConfig] = Singleton(_load_config)

def from_event(event) -> Optional[SpackbotConfig]:
    try:
        repo_name = event.data["repo"]["name"]
    except KeyError:
        logger.error("Malformed event data, expected repo.name")
        return None

    try:
        return CONFIG[repo_name]
    except KeyError:
        logger.error(f"Invalid repo {repo_name}")

    return None
