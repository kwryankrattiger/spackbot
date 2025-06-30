# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import pytest
import re

import spackbot.workers.label as label

@pytest.mark.parametrize(
    "file_data",
    [("lib/spack/spack/component/test.py", "component"), ("not/a/component/object.txt", "")]
)
def test_label_custom_attributes(file_data):
    attribute = {
        "filename": {
            "from": "filename",
            "match": ".*"
        },
        "basename": {
            "from": "filename",
            "match": ".*/([^/]+)$"
        },
        "component": {
            "from": "filename",
            "match": "lib/spack/spack/([^/]+)/?.*.py$"
        },
        "short_component": {
            "from": "component",
            "match": "(.{,4})"
        }
    }


    file = {
        "filename": file_data[0],
        "status": "added",
    }
    assert "basename" not in file
    assert "component" not in file
    assert "short_component" not in file
    label.compute_file_attributes(file, attribute)

    # Make sure the old attirbutes are not modified
    assert file["filename"] == file_data[0]
    assert file["status"] == "added"

    assert "basename" in file
    assert file["basename"] == os.path.basename(file_data[0])
    assert "component" in file
    assert file["component"] == file_data[1]
    assert "short_component" in file
    assert file["short_component"] == file_data[1][:4]


@pytest.mark.parametrize("file_data", [("lib/test.py", ["python", "file"]), ("doc/object.txt", ["file"]), ("no_match", [])])
def test_label_collect_labels(file_data):
    label_patterns = {
        "python": {
            "filename": [re.compile(".*/([^/]+\\.py)$")]
        },
        "file": {
            "filename": [re.compile(".*/([^/]+\\.py)$"), re.compile(".*/([^/]+\\.txt)$")]
        },
    }


    file = {
        "filename": file_data[0],
        "status": "added",
    }
    labels = label.collect_labels(file, label_patterns)

    # All collected labels are in expected
    assert all(l in labels for l in file_data[1])
    # All expected labels are in collected
    assert all(l in file_data[1]for l in labels)


def test_label_worker_async(mock_gh_api):
    pass
