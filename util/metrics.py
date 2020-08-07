
from bson.objectid import ObjectId
from pycoshark.mongomodels import CodeEntityState


def hunk_lines(hunk):
    """Return lists of added/removed lines for the given Hunk object."""
    lno = hunk.new_start - 1
    dlno = hunk.old_start - 1

    lines_added = []
    lines_deleted = []

    for l in hunk.content.split('\n'):
        if not l:
            continue
        if not l.startswith('-'):
            lno += 1
            lines_added.append(lno)
            # print('[{}] {}'.format(lno, l))
        if not l.startswith('+'):
            dlno += 1
            if l.startswith('-'):
                lines_deleted.append(dlno)
                # print('[{}] {}'.format(dlno, l))
    return lines_added, lines_deleted


def get_warning_list(ces_ids):
    ret = []
    c = CodeEntityState.objects().aggregate(*[
            {'$match': {'_id': {'$in': ces_ids}, 'ce_type': 'file'}},
            {'$unwind': '$linter'},
            {'$group': {
                '_id': '$linter.l_ty',
                'sum': {'$sum': 1}
                }
            },
            {'$group': {
                 '_id': 0,
                 'ASAT_warnings': {'$push': {'type': '$_id', 'sum': '$sum'}}
                }
            },
            {
                '$project': {'ASAT_warnings': 1, '_id': 1}
            }
        ])

    try:
        warnings = c.next()
        if 'ASAT_warnings' in warnings.keys():
            ret = warnings['ASAT_warnings']
    except StopIteration:
        pass

    return ret


def get_file_metrics(ces_ids):
    ret = {}
    c = CodeEntityState.objects().aggregate(*[
        {'$match': {'_id': {'$in': ces_ids}, 'ce_type': 'file'}},
        {'$project': {'metrics.LOC': 1,
                      'metrics.McCC': 1,
                      'metrics.LLOC': 1}},
        {'$group': {'_id': 'null',
                    'file_loc_sum': {'$sum': '$metrics.LOC'},
                    'file_loc_avg': {'$avg': '$metrics.LOC'},
                    'file_lloc_sum': {'$sum': '$metrics.LLOC'},
                    'file_lloc_avg': {'$avg': '$metrics.LLOC'},
                    'file_mccc_sum': {'$sum': '$metrics.McCC'},
                    'file_mccc_avg': {'$avg': '$metrics.McCC'}}}
    ])
    try:
        ret = c.next()
    except StopIteration:
        pass

    return ret


def find_narrow_ces(commit, file_id, line):
    """Find the smalles CodeEntityState that corresponds to the changed line, i.e., smalles method containing that line."""
    smallest_size = float('inf')
    smallest_ces = None
    for ces in CodeEntityState.objects.filter(id__in=commit.code_entity_states, file_id=file_id, ce_type='method', start_line__lte=line, end_line__gte=line):
        if ces.end_line - ces.start_line < smallest_size:
            smallest_ces = ces
            smallest_size = ces.end_line - ces.start_line
    return smallest_ces


def get_warnings(commit, file_path):
    """Return list of ASAT warnings for the commit and file path."""
    linter = []
    warnings = {}
    pos_in_file = 1

    try:
        ces = CodeEntityState.objects.get(id__in=commit.code_entity_states, ce_type='file', long_name=file_path)
        linter = ces.linter
    except CodeEntityState.DoesNotExist:
        pass

    for ll in linter:
        # maybe we do not need this if we can detect moves
        # ces = find_narrow_ces(commit, f1.id, ll['ln'])

        key = '{}:{}:{}'.format(file_path, ll['ln'], ll['l_ty'])
        if key not in warnings.keys():
            warnings[key] = []
        warnings[key].append({'file': file_path, 'line': ll['ln'], 'type': ll['l_ty'], 'msg': ll['msg'], 'rel_pos_in_file': pos_in_file})

        pos_in_file += 1

    return warnings


def get_metrics(previous_commit, current_commit, previous_file, current_file):
    """Return metrics delta between two commits and given files."""
    ret = {}
    cparent = CodeEntityState.objects().aggregate(*[
        {'$match': {'_id': {'$in': previous_commit.code_entity_states}, 'ce_type': 'method', 'file_id': ObjectId(previous_file.id)}},
        {'$project': {'metrics.LLOC': 1,
                      'metrics.MIMS': 1,
                      'metrics.McCC': 1}},
        {'$group': {'_id': 'null',
                    'nr_methods': {'$sum': 1},
                    'method_lloc_sum': {'$sum': '$metrics.LLOC'},
                    'method_lloc_avg': {'$avg': '$metrics.LLOC'},
                    'method_mims_sum': {'$sum': '$metrics.MIMS'},
                    'method_mims_avg': {'$avg': '$metrics.MIMS'},
                    'method_mccc_sum': {'$sum': '$metrics.McCC'},
                    'method_mccc_avg': {'$avg': '$metrics.McCC'}}}
    ])

    ccurrent = CodeEntityState.objects().aggregate(*[
        {'$match': {'_id': {'$in': current_commit.code_entity_states}, 'ce_type': 'method', 'file_id': ObjectId(current_file.id)}},
        {'$project': {'metrics.LLOC': 1,
                      'metrics.MIMS': 1,
                      'metrics.McCC': 1}},
        {'$group': {'_id': 'null',
                    'nr_methods': {'$sum': 1},
                    'method_lloc_sum': {'$sum': '$metrics.LLOC'},
                    'method_lloc_avg': {'$avg': '$metrics.LLOC'},
                    'method_mims_sum': {'$sum': '$metrics.MIMS'},
                    'method_mims_avg': {'$avg': '$metrics.MIMS'},
                    'method_mccc_sum': {'$sum': '$metrics.McCC'},
                    'method_mccc_avg': {'$avg': '$metrics.McCC'}}}
    ])

    parent = None
    current = None
    try:
        parent = cparent.next()
    except StopIteration:
        pass

    try:
        current = ccurrent.next()
    except StopIteration:
        pass

    if parent and current:
        for k in parent.keys():
            if k == '_id':
                continue
            ret[k] = parent[k] - current[k]

    return ret


def get_warning_density(commit):
    lloc = 0
    for ces in CodeEntityState.objects.filter(id__in=commit.code_entity_states, ce_type='file'):
        if ces.long_name.lower().endswith('.java'):
            if ces.metrics and 'LLOC' in ces.metrics.keys():
                lloc += ces.metrics['LLOC']

    wd = 0
    if lloc > 0:
        wl = get_warning_list(commit.code_entity_states)
        wd = sum(w['sum'] for w in wl) / lloc
    return wd
