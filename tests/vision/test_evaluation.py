import pytest
from scripts.evaluate_detection import evaluate, validate_manifest


def dataset():
    return {'labels':['chair','person'],'images':[
        {'id':'a','scene_id':'scene-a','split':'tuning','reviewed':True,'complete_for_labels':True,
         'objects':[{'label':'chair','box':[.1,.1,.4,.8]}]},
        {'id':'b','scene_id':'scene-b','split':'validation','reviewed':True,'complete_for_labels':True,'objects':[]} ]}


def test_duplicate_predictions_and_wrong_class_do_not_inflate_recall():
    predictions={'a':[{'label':'chair','box':[.1,.1,.4,.8],'score':.9},
                      {'label':'chair','box':[.1,.1,.4,.8],'score':.8},
                      {'label':'person','box':[.1,.1,.4,.8],'score':.7}], 'b':[]}
    report=evaluate(dataset(),predictions,[.35,.85])
    at35=report['thresholds']['0.35']['tuning']['overall']
    assert at35=={'tp':1,'fp':2,'fn':0,'precision':1/3,'recall':1.}
    assert report['thresholds']['0.85']['tuning']['overall']['fp']==0


def test_miss_and_negative_scene_false_positive_are_recorded():
    predictions={'a':[], 'b':[{'label':'person','box':[0.,0.,.5,.5],'score':.9}]}
    report=evaluate(dataset(),predictions,[.35])['thresholds']['0.35']
    assert report['tuning']['overall']['fn']==1 and report['tuning']['overall']['recall']==0
    assert report['validation']['overall']['fp']==1
    assert report['validation']['overall']['recall'] is None


def test_low_overlap_counts_as_miss_and_false_positive():
    report=evaluate(dataset(),{'a':[{'label':'chair','box':[.8,.8,1.,1.],'score':.9}],'b':[]},[.35])
    counts=report['thresholds']['0.35']['tuning']['overall']
    assert (counts['tp'],counts['fp'],counts['fn'])==(0,1,1)


@pytest.mark.parametrize('change',['unreviewed','incomplete','scene_leak','invalid_box'])
def test_unreviewed_or_leaked_or_invalid_ground_truth_rejected(change):
    data=dataset()
    if change=='unreviewed': data['images'][0]['reviewed']=False
    if change=='incomplete': data['images'][0]['complete_for_labels']=False
    if change=='scene_leak': data['images'][1]['scene_id']='scene-a'
    if change=='invalid_box': data['images'][0]['objects'][0]['box']=[.5,0.,.1,1.]
    with pytest.raises(ValueError): validate_manifest(data)
