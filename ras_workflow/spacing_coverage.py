"""Keep section-end coverage separate from numerical spacing differences."""


def observations(hydraulics, baseline_stations):
    from .qa_locator import collect
    return classify(collect(hydraulics)['rows'], baseline_stations)


def classify(rows, baseline_stations):
    baseline = {float(rs) for rs in baseline_stations}
    wet = [dict(rs=str(float(row['rs'])), profile=row['profile'],
                left_excess_ft=row['left_excess_ft'], right_excess_ft=row['right_excess_ft'])
           for row in rows if row['left_excess_ft'] > 0 or row['right_excess_ft'] > 0]
    stations = sorted({float(row['rs']) for row in wet}, reverse=True)
    return dict(wet_sections=[str(rs) for rs in stations], wet_section_profiles=wet,
                retained_wet_sections=[str(rs) for rs in stations if rs in baseline],
                added_wet_sections=[str(rs) for rs in stations if rs not in baseline])


def assess_coverage(cases):
    incomplete = [case['id'] for case in cases if case.get('status') != 'COMPUTED']
    affected = [dict(id=case['id'], wet_sections=case['wet_sections'],
                     retained_wet_sections=case['retained_wet_sections'],
                     added_wet_sections=case['added_wet_sections'])
                for case in cases if case.get('wet_sections')]
    return dict(status='INCOMPLETE' if incomplete else 'PROVISIONAL_WET_SECTION_ENDS' if affected else 'ENDS_ABOVE_COMPUTED_WATER',
                affected_cases=affected, incomplete_cases=incomplete,
                next_action='COMPLETE_BATCH' if incomplete else 'REVISE_COVERAGE_THEN_REPEAT_SPACING' if affected else 'REVIEW_REMAINING_QA',
                hydraulic_qa='REVIEW_REQUIRED', engineering_acceptance='NOT_ASSESSED')
