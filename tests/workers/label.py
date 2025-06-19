# Copyright 2013-2021 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import os
import pytest

import spackbot.workers.label as label

@pytest.mark.parametrize("file_data", [("lib/spack/spack/component/test.py", "component"), ("not/a/component/object.txt", "")])
def test_label_custom_attributes(file_data):
    attribute = {
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


