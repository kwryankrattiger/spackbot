# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import yaml
import pytest
import spackbot.config as cfg

from gidgethub import sansio

def get_dummy_data(feature):
    if feature == "style":
        return {"style": {"tools": "noop"}}
    elif feature == "pipeline":
        return {"pipeline": {
            "gitlab": "https://gitlab.dummy.io",
        }}
    elif feature == "label":
        return {"label": {
            "extra-attributes": {
                "fname": {
                    "from": "filename",
                    "match": ".*/(.*)\\..*",
                },
            },
            "label-patterns": {
                "fname": {
                    "filename": [".*/(.*)\\..*"]
                },
            }
        }}
    elif feature == "maintainers":
        return {"maintainers": {
            "git": "strategy",
            "packages": True
        }}
    elif feature == "jokes":
        return {"jokes": True}
    else:
        return {feature: False}


@pytest.fixture
def mock_config(tmpdir, monkeypatch):
    dummy_config = {}
    dummy_config.update(get_dummy_data("style"))
    dummy_config.update(get_dummy_data("pipeline"))
    dummy_config.update(get_dummy_data("label"))
    dummy_config.update(get_dummy_data("maintainers"))

    cfg_file = os.path.join(tmpdir, "config.yml")
    with open(cfg_file, "w") as fd:
        yaml.dump({"repo/dummy": dummy_config}, fd)

    monkeypatch.setenv("SPACKBOT_CONFIG_FILE", cfg_file)


@pytest.mark.parametrize("key", ["style", "pipeline", "label", "maintainers", "jokes", "unrecognized"])
def test_config_keys(key):
    if not key == "unrecognized":
        cfg.SpackbotConfig(get_dummy_data(key))
    else:
        with pytest.raises(cfg.SpackbotConfigurationError, match="Dectected unrecognized keys"):
            cfg.SpackbotConfig(get_dummy_data(key))


def test_config_load(mock_config, tmpdir):
    assert "repo/dummy" in cfg.CONFIG
    config = cfg.CONFIG["repo/dummy"]

    assert config.has_feature("style")
    assert config.has_feature("pipeline")
    assert config.has_feature("label")
    assert config.has_feature("maintainers")
    assert not config.has_feature("jokes")

    assert config.style.tools[0] == "noop"


@pytest.mark.parametrize("repo_name", ["repo/dummy", "repo/does_not_exist"])
def test_config_from_event(mock_config, repo_name):
    data = {
        "repository": {
            "full_name": repo_name,
        },
    }
    event = sansio.Event(data, event="test", delivery_id="0")
    config = cfg.from_event(event)

    if "dummy" in repo_name:
        assert config is not None
    else:
        assert config is None
