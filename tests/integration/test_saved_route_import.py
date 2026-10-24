import pytest
pytest.importorskip('stride_backend.route_models',reason='Phase 3 required')
from stride_backend.database import Database
from stride_backend.route_store import RouteCatalog
from stride_backend.errors import BackendError
from scripts.import_saved_route import import_route


def definition():
    return {'route_id':'room-to-desk','name':'Room to desk','checked':True,'verification_note':'Untrusted import claim',
            'checkpoints':[{'checkpoint_id':'entry','ordinal':0,'landmark':'Entry marker',
              'instruction':'TEST FIXTURE instruction only','direction':'stop',
              'return_instruction':'TEST FIXTURE return only','return_direction':'stop','return_checked':True}]}


def test_named_place_route_saved_but_import_cannot_claim_verification(tmp_path):
    db=Database(tmp_path/'routes.sqlite3'); imported=import_route(definition(),db)
    assert imported.checked is False and imported.verification_note is None
    assert imported.checkpoints[0].return_checked is False
    read=RouteCatalog(Database(tmp_path/'routes.sqlite3')).list().routes[0]
    assert read.name=='Room to desk' and read.checkpoints[0].landmark=='Entry marker'
    with pytest.raises(BackendError): import_route(definition(),db)  # Never replace an existing route.
