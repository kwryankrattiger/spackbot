import pytest

import spackbot.actions.label as label

@pytest.mark.parametrize("file_data", [("lib/spack/spack/component/test.py", "component"), ("lib/spack/spack/xx/test.py", "xx")])
def test_label_custom_attributes(file_data):
    attribute = {
        "basename": {
            "from": "filename",
            "match": ".*/([^/]+.py)$"
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
    assert file["basename"] == "test.py"
    assert "component" in file
    assert file["component"] == file_data[1]
    assert "short_component" in file
    assert file["short_component"] == file_data[1][:4]


def test_label_mapping():

