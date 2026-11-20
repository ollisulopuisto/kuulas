"""Acceptance guards are checked before a sync proposal can produce any edit."""

from dataclasses import replace

import pytest

from kuulas.align_apply import validate_acceptance
from kuulas.align_job import snapshot_key
from kuulas.messages import t
from kuulas.model import Clip, Media, Project, Track


def setup():
    media=tuple(Media(id,id,1,4800000) for id in ["ma","mb"])
    project=Project(media=media,tracks=(
        Track("a","A",clips=(Clip("ca","ma",0,0,4800000),)),
        Track("b","B",clips=(Clip("cb","mb",48000,0,4800000),)),))
    result={"snapshot":snapshot_key(project),"reference":"ca","candidates":[
        {"clip":"cb","status":"proposal","timeline_delta":2.,"proposal":
         {"offset":3.,"slope":0.,"support":[0,1,2],"excluded":[]}}]}
    return project,result


def test_accepted_selection_and_snapshot_are_both_required():
    project,result=setup()
    assert validate_acceptance(project,result,["cb"]) == ("cb",)
    with pytest.raises(ValueError,match=t("error.sync.stale")):
        validate_acceptance(replace(project,master_gain_db=-1),result,["cb"])
    with pytest.raises(ValueError,match=t("error.sync.accept_selection")):
        validate_acceptance(project,result,["missing"])


@pytest.mark.parametrize(("field", "value"),[("status","unmatched"),
    ("timeline_delta",float("nan")),("proposal",None)])
def test_invalid_candidate_cannot_be_accepted(field,value):
    project,result=setup()
    result["candidates"][0][field]=value
    with pytest.raises(ValueError,match="proposal"):
        validate_acceptance(project,result,["cb"])


def test_excluded_windows_must_be_explained_before_whole_clip_apply():
    project,result=setup()
    result["candidates"][0]["proposal"]["excluded"]=[2]
    with pytest.raises(ValueError,match=t("error.sync.excluded")):
        validate_acceptance(project,result,["cb"])


def test_duplicate_acceptance_or_reference_as_candidate_is_rejected():
    project,result=setup()
    for selected in [[],["cb","cb"],["ca"]]:
        with pytest.raises(ValueError,match=t("error.sync.accept_selection")):
            validate_acceptance(project,result,selected)
