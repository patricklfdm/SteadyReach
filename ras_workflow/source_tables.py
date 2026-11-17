"""Position-aware FIS table candidates with explicit row and column provenance."""
import re

NUMBER = r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
ROUGHNESS = r'(?:0?\.\d+)(?:\s*[-–]\s*0?\.\d+)?'


def _range(text):
    values = [float(value) for value in re.split(r'\s*[-–]\s*', text)]
    if not all(0 < value < 1 for value in values) or values != sorted(values):
        raise ValueError('Invalid roughness range')
    return [values[0], values[-1]]


def parse(layout, page):
    lines = layout.expandtabs().splitlines()
    title = re.search(r'Table\s+(\d+)\s*[:\-]?\s*(Summary of Discharges|Roughness Coefficients)', layout, re.I)
    if title is None:
        return []
    table = dict(table_number=int(title[1]), title=title[2], pdf_page=page,
                 method='PDF text layout', rows=[], warnings=[])
    if title[2].lower() == 'roughness coefficients':
        if not re.search(r'Channel.+Overbank', layout, re.I):
            table['warnings'].append('Roughness channel/overbank headers could not be identified')
            return [table]
        pattern = re.compile(r'^\s*([A-Za-z][A-Za-z0-9 .()\-/]+?)\s{2,}('+ROUGHNESS+r')\s{2,}('+ROUGHNESS+r')\s*$')
        for line_number, line in enumerate(lines, 1):
            match = pattern.match(line)
            if not match:
                continue
            try:
                channel, overbank = _range(match[2]), _range(match[3])
            except ValueError:
                table['warnings'].append(f'Invalid roughness range on layout line {line_number}')
                continue
            table['rows'].append(dict(kind='roughness', stream=match[1].strip(),
                channel_range=channel, overbank_range=overbank, layout_line=line_number, excerpt=line.strip()))
        return [table]
    header = next((index for index, line in enumerate(lines)
                   if 'Flooding Source' in line and 'Location' in line), None)
    if header is None or not re.search(r'Peak\s+Discharge\s*\(cfs\)', layout, re.I):
        table['warnings'].append('Discharge source/location headers or cfs units could not be identified')
        return [table]
    headers = lines[:header+1]
    columns = []
    for line in headers:
        for match in re.finditer(r'(?<![\d.])1%\s+Annual', line):
            center = (match.start()+match.end())/2
            plus = any(re.search(r'\bPlus\b', row[max(0,int(center)-9):int(center)+10], re.I) for row in headers)
            if not plus:
                columns.append(center)
    if len(columns) != 1:
        table['warnings'].append('A unique ordinary 1% Annual Chance column could not be identified')
        return [table]
    target = columns[0]
    split = int((lines[header].index('Flooding Source')+len('Flooding Source')+lines[header].index('Location'))/2)
    pending_stream, pending_location = [], []
    current = None
    location_end = int(target-20)
    gap = True
    for line_number, line in enumerate(lines[header+1:], header+2):
        if re.match(r'\s*(?:Table\s+\d+\b|Figure\s+\d+\b|\*|Note\b|Source\b)', line, re.I):
            break
        cells = list(re.finditer(r'\S+(?: \S+)*', line))
        numeric = [cell for cell in cells if cell.start() > split and re.fullmatch(NUMBER+r'|\*', cell[0])]
        at_column = [cell for cell in numeric if abs((cell.start()+cell.end())/2-target) <= 7]
        stream = ' '.join(line[:split].split())
        if len(numeric) >= 3 and len(at_column) == 1 and stream:
            location_end = numeric[0].start()
            location = ' '.join(' '.join(pending_location+[line[split:location_end]]).split())
            stream = ' '.join(pending_stream+[stream])
            pending_stream, pending_location = [], []
            current = None
            value = at_column[0][0]
            if value != '*' and float(value.replace(',', '')) > 0:
                current = dict(kind='discharge', stream=stream, location=location,
                    aep_percent=1., flow_cfs=float(value.replace(',', '')), layout_line=line_number,
                    excerpt=line.strip(), column_label='1% Annual Chance', column_center=target)
                table['rows'].append(current)
            gap = False
        elif not line.strip():
            gap = True
        elif re.search(r'[A-Za-z]', line[:location_end]) and not line[location_end:].strip() and not numeric:
            location = ' '.join(line[split:location_end].split())
            if current is not None and not gap:
                current['stream'] = ' '.join(value for value in (current['stream'],stream) if value)
                current['location'] = ' '.join(value for value in (current['location'],location) if value)
                current['excerpt'] += ' / '+line.strip()
            elif gap:
                if stream:pending_stream.append(stream)
                if location:pending_location.append(location)
        else:
            pending_stream, pending_location = [], []
    return [table]


def candidates(tables, scenario_index=0, profile_index=0):
    result = []
    for table in tables:
        for row in table['rows']:
            locus = dict(pdf_page=table['pdf_page'], table_number=table['table_number'],
                         table_title=table['title'], layout_line=row['layout_line'], stream=row['stream'])
            if row['kind'] == 'discharge':
                if profile_index is None:
                    continue
                locus.update(location=row['location'], column_label=row['column_label'])
                result.append(dict(field=f'c.scenarios.{scenario_index}.profiles.{profile_index}.flow_cfs',
                    value=row['flow_cfs'], evidence_class='reported', source_locus=locus,
                    hydrologic_context=dict(stream=row['stream'], location=row['location'], aep_percent=1.),
                    requires_applicability_review=True,
                    basis=f"PDF page {table['pdf_page']}, Table {table['table_number']}, {row['stream']}, {row['location']}, 1% Annual Chance, cfs. Confirm that this hydrologic location applies to the modeled reach."))
            else:
                for field, name in [('channel_n','channel'),('overbank_n','overbank')]:
                    interval = row[name+'_range']
                    assumed = interval[0] != interval[1]
                    basis = (f"PDF page {table['pdf_page']}, Table {table['table_number']}, {row['stream']}, {name} n {interval[0]:g}–{interval[1]:g}. "
                             + ('Conditional midpoint of the reported range. Check vegetation, material and depth.' if assumed else 'Reported coefficient. Check reach applicability.'))
                    result.append(dict(field=f'c.scenarios.{scenario_index}.{field}', value=round(sum(interval)/2,6),
                        evidence_class='assumed' if assumed else 'reported', range=interval, source_locus=locus,
                        hydrologic_context=dict(stream=row['stream']), requires_applicability_review=True, basis=basis))
    return result
