import pytest
from pydantic import ValidationError

from ariano_api.models import DemandIn


def test_valid_demand_trims_title():
    demand = DemandIn.model_validate({
        "title": "  Oportunidade de inovação  ",
        "tags": [{"tag_id": 1, "type": "REQUIRED", "weight": 1}],
    })
    assert demand.title == "Oportunidade de inovação"


@pytest.mark.parametrize("payload", [
    {"title": "Edital válido", "tags": []},
    {"title": "   ", "tags": [{"tag_id": 1, "weight": 1}]},
    {"title": "  a  ", "tags": [{"tag_id": 1, "weight": 1}]},
    {"title": "Edital válido", "tags": [{"tag_id": 1, "weight": 0}]},
    {"title": "Edital válido", "tags": [{"tag_id": 1, "weight": 1}, {"tag_id": 1, "weight": 2}]},
    {"title": "Edital válido", "budget": -1, "tags": [{"tag_id": 1, "weight": 1}]},
])
def test_invalid_demand_is_rejected(payload):
    with pytest.raises(ValidationError):
        DemandIn.model_validate(payload)

