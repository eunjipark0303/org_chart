import os
from flask import Flask, render_template, jsonify, request
from datetime import datetime
from sheets_client import get_employees, build_flat_tree

app = Flask(__name__)
app.json.sort_keys = False

CORPS = ['에임드', '게임베리스튜디오', '마티니', '뉴플레이']
CORP_ORDER = ['전체'] + CORPS


@app.route('/')
def index():
    today = datetime.today().strftime('%Y-%m-%d')
    return render_template('index.html', today=today, corp_order=CORP_ORDER)


@app.route('/api/orgchart')
def orgchart():
    date = request.args.get('date', datetime.today().strftime('%Y-%m-%d'))
    corp = request.args.get('corp', '전체')

    try:
        employees = get_employees(date)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    corp_counts = {}
    for e in employees:
        c = e['corp'] or '기타'
        corp_counts[c] = corp_counts.get(c, 0) + 1

    total = len(employees)

    if corp == '전체':
        sections = {}
        for c in CORPS:
            nodes = build_flat_tree(employees, c)
            sections[c] = {
                'nodes': nodes,
                'count': sum(1 for n in nodes if not n.get('is_virtual')),
            }
        return jsonify({
            'corp':        '전체',
            'total':       total,
            'corp_counts': corp_counts,
            'sections':    sections,
        })

    nodes = build_flat_tree(employees, corp)
    return jsonify({
        'corp':        corp,
        'total':       total,
        'count':       sum(1 for n in nodes if not n.get('is_virtual')),
        'corp_counts': corp_counts,
        'nodes':       nodes,
    })



@app.route('/api/debug/skipped')
def debug_skipped():
    """조직도에서 제외된 인원과 사유를 반환 (진단용)"""
    date = request.args.get('date', datetime.today().strftime('%Y-%m-%d'))
    try:
        employees, skipped = get_employees(date, debug=True)
        return jsonify({'date': date, 'included_count': len(employees), 'skipped': skipped})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port)
