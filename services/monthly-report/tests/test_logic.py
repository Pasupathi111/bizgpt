"""Business logic and AI-output normalisation (no model, no network)."""

import pytest

from app import ai, logic

PROJECT = {'id': 'p', 'name': 'Test Park', 'zones': ['Zone A', 'Zone B']}
WORK = ['Grass Cutting', 'Tree Maintenance']


def photo(pid, stage, location, work='Grass Cutting', conf=90, **extra):
    return {
        'id': pid, 'filename': f'{pid}.jpg', 'status': 'analyzed', 'excluded': False, 'reviewed': False, 'overrides': {},
        'exif_datetime': None,
        'ai': {'stage': stage, 'stage_confidence': conf if stage else 0, 'location': location,
               'location_confidence': conf if location else 0, 'work_type': work, 'work_type_confidence': conf if work else 0,
               'issues': [], 'description': 'x', 'datetime_text': None},
        **extra,
    }


def test_parse_json_handles_fences_and_prose():
    assert ai.parse_json('Sure!\n```json\n{"a": "b \\" }"}\n```') == {'a': 'b " }'}


def test_parse_json_rejects_garbage():
    with pytest.raises(ai.ModelError):
        ai.parse_json('no json here')


def test_normalise_never_keeps_values_outside_the_project():
    raw = {'stage': 'before', 'stage_confidence': 0.94, 'visible_text': 'ZONE Z', 'location': 'Zone A',
           'work_type': 'grass cutting', 'work_type_confidence': '88', 'issues': ['None'], 'condition': 'untidy'}
    out = ai.normalise_photo(raw, PROJECT, WORK)
    assert out['stage'] == 'BEFORE' and out['stage_confidence'] == 94
    assert out['location'] is None and out['location_confidence'] == 0  # model's own "location" is ignored
    assert out['work_type'] == 'Grass Cutting' and out['work_type_confidence'] == 88
    assert out['issues'] == [] and out['datetime_text'] is None


def test_location_and_date_come_from_visible_text():
    raw = {'stage': 'AFTER', 'stage_confidence': 90, 'condition': 'tidy', 'visible_text': 'ZONE B\nTaman Park - Zone B   2026-09-10 12:20'}
    out = ai.normalise_photo(raw, PROJECT, WORK)
    assert (out['location'], out['location_confidence'], out['datetime_text']) == ('Zone B', 95, '2026-09-10 12:20')
    assert ai.find_location('Zone A ... Zone B', PROJECT['zones']) == (None, None)  # conflicting signs
    assert ai.find_location('ZONE AB', PROJECT['zones']) == (None, None)


def test_stage_that_contradicts_observations_loses_confidence():
    raw = {'stage': 'BEFORE', 'stage_confidence': 90, 'people_working': True, 'condition': 'untidy'}
    out = ai.normalise_photo(raw, PROJECT, WORK)
    assert out['stage_confidence'] == 50 and out['stage_conflicts'] == ['a person is working in the photo']


def test_normalise_survives_wrong_types():
    out = ai.normalise_photo({'stage': 7, 'issues': 'Broken bench', 'stage_confidence': 'high'}, PROJECT, WORK)
    assert out['stage'] is None and out['issues'] == ['Broken bench']


def test_work_type_outlier_in_a_zone_needs_review():
    photos = [photo('1', 'BEFORE', 'Zone A'), photo('2', 'AFTER', 'Zone A'), photo('3', 'AFTER', 'Zone A', work='Tree Maintenance')]
    majority = logic.work_type_majority(photos)
    assert majority == {'Zone A': 'Grass Cutting'}
    assert logic.review_reasons(photos[2], 75, majority) == ['Work type Tree Maintenance differs from the other Zone A photos (Grass Cutting)']
    assert logic.review_reasons(photos[0], 75, majority) == []


def test_grouping_and_missing_during_photo():
    photos = [photo('1', 'BEFORE', 'Zone A'), photo('2', 'DURING', 'Zone A'), photo('3', 'AFTER', 'Zone A'),
              photo('4', 'BEFORE', 'Zone B'), photo('5', 'AFTER', 'Zone B')]
    groups = {g['location']: g['stages'] for g in logic.group(photos, PROJECT['zones'])}
    assert groups['Zone A']['DURING'] == ['2']
    v = logic.validate(photos, PROJECT['zones'], ai.STAGES)
    assert v['missing'] == ['Zone B: During photo missing']
    zone_b = next(loc for loc in v['locations'] if loc['location'] == 'Zone B')
    assert [c['ok'] for c in zone_b['checks']] == [True, False, True]


def test_unassigned_and_empty_zone_are_reported():
    v = logic.validate([photo('1', 'BEFORE', None)], PROJECT['zones'], ai.STAGES)
    assert 'Zone A: no photos uploaded' in v['missing']
    assert '1 photo(s) have no location' in v['missing']


def test_low_confidence_needs_review_until_human_corrects():
    p = photo('1', 'BEFORE', 'Zone A', conf=60)
    assert logic.review_reasons(p, 75)
    p['overrides'] = {'location': 'Zone A', 'stage': 'BEFORE', 'work_type': 'Grass Cutting'}
    assert logic.effective(p)['location_source'] == 'human'
    assert logic.review_reasons(p, 75) == []


def test_reviewed_or_excluded_photos_do_not_block():
    p = photo('1', None, None, conf=10)
    assert logic.review_reasons(p, 75)
    assert logic.review_reasons({**p, 'reviewed': True}, 75) == []
    assert logic.review_reasons({**p, 'excluded': True}, 75) == []


def test_failed_analysis_needs_review():
    p = {**photo('1', None, None), 'status': 'error', 'error': 'timeout', 'ai': None}
    assert logic.review_reasons(p, 75) == ['AI analysis failed: timeout']


def test_approval_blockers():
    views = [{'needs_review': True}]
    assert logic.approval_blockers({'content': None}, views) == ['Generate the report first', '1 photo(s) still need human review']
    assert logic.approval_blockers({'content': {'sections': {}}}, [{'needs_review': False}]) == []


def test_intent_is_validated_against_the_report():
    cfg = {'projects': [{'id': 'taman-park', 'name': 'Taman Park Landscape Maintenance'}], 'work_types': WORK}
    photos = [{'id': 'p1', 'filename': 'IMG_0103.jpg'}, {'id': 'p2', 'filename': 'IMG_0104.jpg'}]
    raw = {'action': 'update_photos', 'changes': [
        {'photo': '0103', 'stage': 'during', 'location': 'Zone Q'},  # invented zone is dropped
        {'photo': 'IMG_9999', 'stage': 'AFTER'},
        {'photo': 'IMG_0104.jpg', 'work_type': 'grass cutting', 'exclude': True}]}
    out = ai.normalise_intent(raw, cfg, photos, PROJECT['zones'], '0103 is during, exclude IMG_0104 (grass cutting)')
    assert out['changes'] == [{'photo_id': 'p1', 'filename': 'IMG_0103.jpg', 'stage': 'DURING'},
                              {'photo_id': 'p2', 'filename': 'IMG_0104.jpg', 'work_type': 'Grass Cutting', 'exclude': True}]
    assert out['unknown_photos'] == ['IMG_9999']
    start = ai.normalise_intent({'action': 'start', 'project': 'Taman Park Landscape Maintenance', 'month': '2026-9'}, cfg, [], [])
    assert start == {'action': 'start', 'project_id': 'taman-park', 'month': '2026-09'}
    assert ai.normalise_intent({'action': 'launch rockets'}, cfg, [], [])['action'] == 'help'


def test_decisions_are_never_inferred_from_other_text():
    cfg = {'projects': [], 'work_types': WORK}
    text = 'Change the remarks to: Zone B During photo was not taken this month.'
    out = ai.normalise_intent({'action': 'reject', 'reason': 'photo not taken'}, cfg, [], [], text)
    assert out == {'action': 'set_text', 'section': 'remarks', 'text': 'Zone B During photo was not taken this month.'}
    assert ai.normalise_intent({'action': 'approve'}, cfg, [], [], 'looks fine I guess')['action'] == 'help'
    assert ai.normalise_intent({'action': 'approve'}, cfg, [], [], 'Approve the report')['action'] == 'approve'
    assert ai.normalise_intent({'action': 'reject', 'reason': 'x'}, cfg, [], [], 'reject it: wrong zone')['action'] == 'reject'



def test_chat_project_and_month_must_be_said():
    cfg = {'projects': [{'id': 'taman-park', 'name': 'Taman Park Landscape Maintenance'}], 'work_types': WORK}
    guessed = ai.normalise_intent({'action': 'gmail_import', 'project': 'taman-park', 'month': '2026-09'}, cfg, [], [],
                                  'Get the site photos from Gmail')
    assert guessed == {'action': 'gmail_import', 'project_id': None, 'month': None}
    said = ai.normalise_intent({'action': 'gmail_import', 'project': 'taman-park', 'month': '2026-09'}, cfg, [], [],
                               'Get the Taman Park September 2026 photos from Gmail')
    assert said == {'action': 'gmail_import', 'project_id': 'taman-park', 'month': '2026-09'}


def test_intent_keeps_only_fields_the_message_mentions():
    cfg = {'projects': [], 'work_types': WORK}
    photos = [{'id': 'p1', 'filename': 'IMG_0304.jpg'}]
    # The model added a stage and exclude=false that the coordinator never said.
    raw = {'action': 'update_photos', 'changes': [
        {'photo': 'IMG_0304.jpg', 'stage': 'DURING', 'work_type': 'grass cutting', 'exclude': False}]}
    out = ai.normalise_intent(raw, cfg, photos, PROJECT['zones'], 'IMG_0304 is grass cutting')
    assert out['changes'] == [{'photo_id': 'p1', 'filename': 'IMG_0304.jpg', 'work_type': 'Grass Cutting'}]


def test_status_intent_keeps_the_month_the_user_named():
    cfg = {'projects': [{'id': 'taman-park', 'name': 'Taman Park Landscape Maintenance'}], 'work_types': WORK}
    out = ai.normalise_intent({'action': 'status', 'month': '2026-10'}, cfg, [], [], 'show me the October month report')
    assert out == {'action': 'status', 'project_id': None, 'month': '2026-10'}
    # a month the user did not write is never kept
    assert ai.normalise_intent({'action': 'status', 'month': '2026-10'}, cfg, [], [], 'show my report')['month'] is None
