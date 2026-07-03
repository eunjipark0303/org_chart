import os
import json
import base64
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# ── 법인 표시명 매핑 ──────────────────────────────────────────────
CORP_DISPLAY = {'스튜디오': '게임베리스튜디오'}

# ── 팀/법인별 색상 ────────────────────────────────────────────────
TEAM_COLORS = {
    # 에임드 법인 루트
    '에임드':          '#6366f1',
    # 에임드 팀
    '이클립스':        '#4338ca',
    '이클립스팀':      '#4338ca',
    '퍼즐팀':          '#7c3aed',
    'AI개발팀':        '#0891b2',
    'UA팀':            '#065f46',
    '마케팅파트':      '#059669',
    '크리에이티브파트': '#0d9488',
    '게임운영팀':      '#0369a1',
    '디자인팀':        '#be185d',
    '재무팀':          '#b45309',
    '피플팀':          '#dc2626',
    # 게임베리스튜디오
    '게임베리스튜디오': '#10b981',
    '블랙':            '#374151',
    '골든':            '#92400e',
    '레드':            '#991b1b',
    # 마티니
    '마티니':          '#f59e0b',
    'CRM팀':           '#6d28d9',
    'BA팀':            '#1e40af',
    '세일즈팀':        '#166534',
    'CSM팀':           '#92400e',
    # 뉴플레이
    '뉴플레이':        '#ef4444',
    '서비스개발':      '#1e3a8a',
    '기획팀':          '#5b21b6',
}

# ── 에임드 팀 정렬 순서 ───────────────────────────────────────────
AIMED_DEPT_ORDER = [
    '에임드',
    '이클립스', '이클립스팀',
    '퍼즐팀',
    'AI개발팀',
    '게임운영팀',
    'UA팀', '마케팅파트', '크리에이티브파트',
    '디자인팀',
    '재무팀',
    '피플팀',
]
_AIMED_ORDER_MAP = {d: i for i, d in enumerate(AIMED_DEPT_ORDER)}


def _get_service():
    creds_b64 = os.getenv('GOOGLE_CREDENTIALS_B64')
    if creds_b64:
        info = json.loads(base64.b64decode(creds_b64).decode('utf-8'))
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(
            os.getenv('CREDENTIALS_FILE'), scopes=SCOPES
        )
    return build('sheets', 'v4', credentials=creds, cache_discovery=False)


def _get_transfer_overrides(service, ref_date) -> dict:
    """부서이동이력 시트에서 ref_date 기준으로 아직 발생하지 않은 이동의 이전 부서 반환"""
    result = service.spreadsheets().values().get(
        spreadsheetId=os.getenv('HR_SHEET_ID'),
        range='부서이동이력!A2:F1000'
    ).execute()
    rows = result.get('values', [])

    candidates = {}
    for row in rows:
        if len(row) < 2 or not row[0]:
            continue
        name = row[0].strip()
        raw = row[1].strip().replace('.', '-').replace('/', '-').replace(' ', '')
        try:
            change_date = datetime.strptime(raw, '%Y-%m-%d').date()
        except ValueError:
            continue
        if change_date <= ref_date:
            continue
        from_dept = row[2].strip() if len(row) > 2 else ''
        from_sub  = row[3].strip() if len(row) > 3 else ''
        # 여러 건이면 가장 가까운 미래 이동 기준으로 보정
        if name not in candidates or change_date < candidates[name][0]:
            candidates[name] = (change_date, from_dept, from_sub)

    return {name: {'dept': v[1], 'sub_dept': v[2]} for name, v in candidates.items()}


def get_employees(reference_date_str: str) -> list[dict]:
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=os.getenv('HR_SHEET_ID'),
        range='인사데이터(평가, 조직도용)!A1:K2000'
    ).execute()
    rows = result.get('values', [])
    if not rows:
        return []

    ref_date = datetime.strptime(reference_date_str, '%Y-%m-%d').date()
    overrides = _get_transfer_overrides(service, ref_date)

    employees = []
    for row in rows[1:]:
        if len(row) < 8:
            continue

        name       = row[0].strip() if row[0] else ''
        corp_raw   = row[1].strip() if len(row) > 1 else ''
        dept       = row[2].strip() if len(row) > 2 else ''
        sub_dept   = row[3].strip() if len(row) > 3 else ''
        supervisor = row[5].strip() if len(row) > 5 else ''
        role       = row[6].strip() if len(row) > 6 else ''
        join_str   = row[7].strip() if len(row) > 7 else ''
        exit_str   = row[8].strip() if len(row) > 8 else ''
        note       = row[10].strip() if len(row) > 10 else ''

        if not name or not join_str:
            continue

        try:
            join_date = datetime.strptime(join_str, '%Y-%m-%d').date()
        except ValueError:
            continue

        if join_date > ref_date:
            continue

        if exit_str:
            try:
                exit_date = datetime.strptime(exit_str, '%Y-%m-%d').date()
                if exit_date < ref_date:
                    continue
            except ValueError:
                pass

        # 쉼표 구분 상위직책자 → 첫 번째만
        if ',' in supervisor:
            supervisor = supervisor.split(',')[0].strip()

        corp = CORP_DISPLAY.get(corp_raw, corp_raw)

        # 부서이동이력 기준 부서/파트 보정
        if name in overrides:
            dept     = overrides[name]['dept']
            sub_dept = overrides[name]['sub_dept']

        employees.append({
            'name':       name,
            'corp':       corp,
            'dept':       dept,
            'sub_dept':   sub_dept,
            'supervisor': supervisor if supervisor and supervisor != '-' else '',
            'role':       role,
            'join_date':  join_str,
            'exit_date':  exit_str,
            'note':       note,
        })

    return employees


def _team_color(dept: str, corp: str) -> str:
    return TEAM_COLORS.get(dept) or TEAM_COLORS.get(corp) or '#94a3b8'


def _make_node(emp: dict, parent: str, *, is_virtual=False) -> dict:
    return {
        'id':         emp['name'],
        'parent':     parent,
        'name':       emp['name'],
        'role':       emp['role'],
        'dept':       emp['dept'],
        'sub_dept':   emp.get('sub_dept', ''),
        'corp':       emp['corp'],
        'note':       emp['note'],
        'join_date':  emp['join_date'],
        'is_virtual': is_virtual,
        'color':      _team_color(emp['dept'], emp['corp']),
    }


def _make_virtual(vid: str, parent: str, name: str, role: str,
                  dept: str, corp: str) -> dict:
    return {
        'id':         vid,
        'parent':     parent,
        'name':       name,
        'role':       role,
        'dept':       dept,
        'sub_dept':   '',
        'corp':       corp,
        'note':       '',
        'join_date':  '',
        'is_virtual': True,
        'color':      _team_color(dept, corp),
    }


# ══════════════════════════════════════════════════════════════════
#  에임드 전용 가상 노드 주입
# ══════════════════════════════════════════════════════════════════

def _inject_ua_structure(nodes: list[dict], id_map: dict):
    """UA팀을 마케팅파트·크리에이티브파트로 분리"""
    ua_v  = _make_virtual('__UA팀__',            '임형철',   'UA팀',           '',             'UA팀',            '에임드')
    mkt_v = _make_virtual('__마케팅파트__',       '__UA팀__', '마케팅파트',      '파트장: 이혜민', '마케팅파트',      '에임드')
    cre_v = _make_virtual('__크리에이티브파트__', '__UA팀__', '크리에이티브파트', '파트장: 김소현', '크리에이티브파트', '에임드')

    for n in nodes:
        if n['id'] == '이혜민':
            n['parent'] = '__마케팅파트__'
        elif n['id'] == '김소현':
            n['parent'] = '__크리에이티브파트__'
        elif n['dept'] == 'UA팀' and n['sub_dept'] == '마케팅파트' and n['parent'] == '임형철':
            n['parent'] = '__마케팅파트__'
        elif n['dept'] == 'UA팀' and n['sub_dept'] == '크리에이티브파트' and n['parent'] == '임형철':
            n['parent'] = '__크리에이티브파트__'

    nodes.extend([ua_v, mkt_v, cre_v])
    id_map.update({'__UA팀__': ua_v, '__마케팅파트__': mkt_v, '__크리에이티브파트__': cre_v})


def _inject_ai_vacancy(nodes: list[dict], id_map: dict):
    """AI개발팀 팀장 공석 가상 노드"""
    ai_v = _make_virtual('__AI개발팀__', '임형철', 'AI개발팀', '팀장 공석', 'AI개발팀', '에임드')
    for n in nodes:
        if n['id'] == '박지수':
            n['parent'] = '__AI개발팀__'
    nodes.append(ai_v)
    id_map['__AI개발팀__'] = ai_v


def _inject_game_ops_vacancy(nodes: list[dict], id_map: dict):
    """게임운영팀 팀장 공석 가상 노드 및 팀원 라우팅"""
    go_v = _make_virtual('__게임운영팀__', '임형철', '게임운영팀', '팀장 공석', '게임운영팀', '에임드')
    for n in nodes:
        if n['dept'] == '게임운영팀':
            n['parent'] = '__게임운영팀__'
    nodes.append(go_v)
    id_map['__게임운영팀__'] = go_v


def _inject_aimed_team_headers(nodes: list[dict], id_map: dict):
    """에임드 각 팀의 가상 헤더 노드 주입 (팀명 → 리더 → 팀원 구조)"""
    # 팀 dept → 가상 노드 ID 매핑
    dept_to_vid = {
        '이클립스':   '__이클립스__',
        '이클립스팀': '__이클립스__',
        '퍼즐팀':     '__퍼즐팀__',
        '디자인팀':   '__디자인팀__',
        '재무팀':     '__재무팀__',
        '피플팀':     '__피플팀__',
    }

    # 임형철 직속 노드를 해당 팀 헤더로 이동
    for n in nodes:
        if n['id'] == '임형철' or n['parent'] != '임형철':
            continue
        vid = dept_to_vid.get(n['dept'])
        if vid:
            n['parent'] = vid

    # 가상 팀 헤더 노드 생성 (DFS 정렬을 위해 dept 값을 AIMED_DEPT_ORDER에 맞게 설정)
    v_nodes = [
        _make_virtual('__이클립스__', '임형철', '이클립스팀', '', '이클립스팀', '에임드'),
        _make_virtual('__퍼즐팀__',   '임형철', '퍼즐팀',     '', '퍼즐팀',     '에임드'),
        _make_virtual('__디자인팀__', '임형철', '디자인팀',   '', '디자인팀',   '에임드'),
        _make_virtual('__재무팀__',   '임형철', '재무팀',     '', '재무팀',     '에임드'),
        _make_virtual('__피플팀__',   '임형철', '피플팀',     '', '피플팀',     '에임드'),
    ]
    nodes.extend(v_nodes)
    for v in v_nodes:
        id_map[v['id']] = v


# ══════════════════════════════════════════════════════════════════
#  게임베리스튜디오 전용 가상 노드 주입
# ══════════════════════════════════════════════════════════════════

def _ensure_im_hyeongcheol(nodes: list[dict], id_map: dict, all_employees: list[dict]):
    """게임베리스튜디오·뉴플레이 뷰에서 임형철을 최상위 노드로 추가하고 고아 노드 연결"""
    if '임형철' in id_map:
        return
    im = next((e for e in all_employees if e['name'] == '임형철'), None)
    if not im:
        return
    im_node = {
        'id': '임형철', 'parent': '',
        'name': '임형철', 'role': '대표이사',
        'dept': '에임드', 'corp': '에임드',
        'sub_dept': '', 'note': '임원', 'join_date': im['join_date'],
        'is_virtual': False,
        'color': TEAM_COLORS.get('에임드', '#6366f1'),
    }
    nodes.insert(0, im_node)
    id_map['임형철'] = im_node

    # 부모가 없는 모든 노드를 임형철 하위로 연결
    # (자기 자신을 상위직책자로 설정한 팀 리더 포함)
    for n in nodes:
        if n['id'] == '임형철' or n['parent']:
            continue
        n['parent'] = '임형철'


def _inject_gb_structure(nodes: list[dict], id_map: dict):
    """게임베리스튜디오 블랙/골든/레드 팀 가상 헤더 노드 주입"""
    black_v  = _make_virtual('__블랙__', '임형철', '블랙팀', '', '블랙', '게임베리스튜디오')
    golden_v = _make_virtual('__골든__', '임형철', '골든팀', '', '골든', '게임베리스튜디오')
    red_v    = _make_virtual('__레드__', '임형철', '레드팀', '', '레드', '게임베리스튜디오')

    for n in nodes:
        if n['id'] == '임형철':
            continue
        if n['dept'] == '블랙' and n['parent'] == '임형철':
            n['parent'] = '__블랙__'
        elif n['dept'] == '골든' and n['parent'] == '임형철':
            n['parent'] = '__골든__'
        elif n['dept'] == '레드' and n['parent'] == '임형철':
            n['parent'] = '__레드__'

    # 블랙팀 flatten: 이민희 직속 팀원을 __블랙__ 하위로 끌어올림
    for n in nodes:
        if n['dept'] == '블랙' and n['parent'] == '이민희':
            n['parent'] = '__블랙__'

    # 블랙팀 순서: 이민희(0) → 전은주(1) → 나머지 (flat list 내 위치 재정렬)
    _BLACK_PRIORITY = {'이민희': 0, '전은주': 1}
    black_pairs = [(i, nodes[i]) for i in range(len(nodes)) if nodes[i].get('parent') == '__블랙__']
    if black_pairs:
        sorted_pairs = sorted(black_pairs, key=lambda x: (_BLACK_PRIORITY.get(x[1]['id'], 2), x[0]))
        for pos, (_, node) in zip([i for i, _ in black_pairs], sorted_pairs):
            nodes[pos] = node

    nodes.extend([black_v, golden_v, red_v])
    id_map.update({'__블랙__': black_v, '__골든__': golden_v, '__레드__': red_v})


# ══════════════════════════════════════════════════════════════════
#  마티니 전용 가상 노드 주입
# ══════════════════════════════════════════════════════════════════

def _inject_martini_structure(nodes: list[dict], id_map: dict):
    """
    이선규(대표) → 이건희(COO) → 4개 팀 가상 헤더
    CRM·CSM·세일즈팀에는 겸직 리더 가상 노드 추가
    CRM팀 하위에 CRM1(공석)/CRM2/CRM3 파트, BA팀 하위에 BA파트1/2
    """
    # 4개 팀 헤더 (이건희 COO 하위)
    crm_v  = _make_virtual('__CRM팀__',   '이건희', 'CRM팀',   '', 'CRM팀',   '마티니')
    ba_v   = _make_virtual('__BA팀__',    '이건희', 'BA팀',    '', 'BA팀',    '마티니')
    csm_v  = _make_virtual('__CSM팀__',   '이건희', 'CSM팀',   '', 'CSM팀',   '마티니')
    sale_v = _make_virtual('__세일즈팀__', '이건희', '세일즈팀', '', '세일즈팀', '마티니')

    # 겸직 리더 가상 노드
    crm_lead  = _make_virtual('__CRM팀장__',   '__CRM팀__',   '이건희', '팀장 (겸직)', 'CRM팀',   '마티니')
    csm_lead  = _make_virtual('__CSM팀장__',   '__CSM팀__',   '이건희', '팀장 (겸직)', 'CSM팀',   '마티니')
    sale_lead = _make_virtual('__세일즈팀장__', '__세일즈팀__', '이선규', '팀장 (겸직)', '세일즈팀', '마티니')

    # CRM 파트 (CRM팀장 하위) — CRM1은 공석
    crm1 = _make_virtual('__CRM1__', '__CRM팀장__', 'CRM1', '공석', 'CRM팀', '마티니')
    crm2 = _make_virtual('__CRM2__', '__CRM팀장__', 'CRM2', '',     'CRM팀', '마티니')
    crm3 = _make_virtual('__CRM3__', '__CRM팀장__', 'CRM3', '',     'CRM팀', '마티니')

    # BA 파트 (김진한 하위)
    ba1 = _make_virtual('__BA파트1__', '김진한', 'BA파트1', '', 'BA팀', '마티니')
    ba2 = _make_virtual('__BA파트2__', '김진한', 'BA파트2', '', 'BA팀', '마티니')

    for n in nodes:
        dept = n['dept']
        sub  = n.get('sub_dept', '')
        nid  = n['id']

        # 이건희: 이선규 직속 COO 유지 (재라우팅 없음)
        if nid == '김진한':           # BA팀 헤드 → __BA팀__ 하위
            n['parent'] = '__BA팀__'
        elif dept == 'CSM팀':         # CSM 팀원 → 이건희 겸직 리더 하위
            n['parent'] = '__CSM팀장__'
        elif dept == '세일즈팀':       # 세일즈 팀원 → 이선규 겸직 리더 하위
            n['parent'] = '__세일즈팀장__'
        elif dept == 'CRM팀' and n['parent'] == '이건희':
            # sub_dept 값으로 CRM 파트 배정 (CRM1은 공석)
            if sub == 'CRM2':
                n['parent'] = '__CRM2__'
            elif sub == 'CRM3':
                n['parent'] = '__CRM3__'
        elif dept == 'BA팀' and n['parent'] == '김진한':
            if sub in ('BA1', 'BA파트1'):
                n['parent'] = '__BA파트1__'
            elif sub in ('BA2', 'BA파트2'):
                n['parent'] = '__BA파트2__'

    nodes.extend([
        crm_v, ba_v, csm_v, sale_v,
        crm_lead, csm_lead, sale_lead,
        crm1, crm2, crm3,
        ba1, ba2,
    ])
    id_map.update({
        '__CRM팀__': crm_v, '__BA팀__': ba_v, '__CSM팀__': csm_v, '__세일즈팀__': sale_v,
        '__CRM팀장__': crm_lead, '__CSM팀장__': csm_lead, '__세일즈팀장__': sale_lead,
        '__CRM1__': crm1, '__CRM2__': crm2, '__CRM3__': crm3,
        '__BA파트1__': ba1, '__BA파트2__': ba2,
    })


# ══════════════════════════════════════════════════════════════════
#  뉴플레이 전용 가상 노드 주입
# ══════════════════════════════════════════════════════════════════

def _inject_newplay_structure(nodes: list[dict], id_map: dict):
    """뉴플레이 팀 가상 헤더 노드 주입 (서비스개발/세일즈팀/기획팀)"""
    sd_v   = _make_virtual('__NP서비스개발__', '임형철', '서비스개발', '', '서비스개발', '뉴플레이')
    sale_v = _make_virtual('__NP세일즈팀__',   '임형철', '세일즈팀',   '', '세일즈팀',   '뉴플레이')
    plan_v = _make_virtual('__NP기획팀__',     '임형철', '기획팀',     '', '기획팀',     '뉴플레이')

    for n in nodes:
        if n['id'] == '임형철' or n['parent'] != '임형철':
            continue
        if n['dept'] == '서비스개발':
            n['parent'] = '__NP서비스개발__'
        elif n['dept'] == '세일즈팀':
            n['parent'] = '__NP세일즈팀__'
        elif n['dept'] == '기획팀':
            n['parent'] = '__NP기획팀__'

    nodes.extend([sd_v, sale_v, plan_v])
    id_map.update({'__NP서비스개발__': sd_v, '__NP세일즈팀__': sale_v, '__NP기획팀__': plan_v})


# ══════════════════════════════════════════════════════════════════
#  에임드 DFS 정렬
# ══════════════════════════════════════════════════════════════════

def _eclipse_role_key(role: str) -> int:
    """이클립스팀 멤버 role → 기획(0)→개발(1)→QA(2)→Art(3) 정렬 키"""
    r = role.lower()
    if '기획' in role or 'game designer' in r or 'game director' in r:
        return 0
    if 'programmer' in r or '개발' in role or '클라이언트' in role:
        return 1
    if 'qa' in r:
        return 2
    if 'artist' in r or '아티스트' in role or 'fx' in r or '에니메이터' in role or 'ui 디자이너' in role:
        return 3
    return 4


def _sort_dfs(nodes: list[dict], order_map: dict) -> list[dict]:
    """DFS 순회 결과를 에임드 팀 순서에 맞게 정렬해 반환"""
    id_to_node = {n['id']: n for n in nodes}
    children: dict[str, list[dict]] = {n['id']: [] for n in nodes}
    roots = []

    for n in nodes:
        p = n['parent']
        if p and p in id_to_node:
            children[p].append(n)
        else:
            roots.append(n)

    def sort_key(n):
        dept_key = order_map.get(n['dept'], 999)
        # 이클립스팀 멤버는 role 기준 2차 정렬 (기획→개발→QA→Art)
        if n['dept'] in ('이클립스', '이클립스팀'):
            return (dept_key, _eclipse_role_key(n.get('role', '')))
        return (dept_key, 0)

    for lst in children.values():
        lst.sort(key=sort_key)
    roots.sort(key=sort_key)

    result = []
    def dfs(n):
        result.append(n)
        for c in children[n['id']]:
            dfs(c)

    for r in roots:
        dfs(r)
    return result


# ══════════════════════════════════════════════════════════════════
#  메인 트리 빌더
# ══════════════════════════════════════════════════════════════════

def build_flat_tree(employees: list[dict], filter_corp: str | None = None) -> list[dict]:
    if filter_corp:
        visible = [e for e in employees if e['corp'] == filter_corp]
    else:
        visible = employees

    visible_names = {e['name'] for e in visible}

    nodes: list[dict] = []
    id_map: dict[str, dict] = {}

    for emp in visible:
        sup = emp['supervisor']
        # 자기 자신을 상위직책자로 설정한 경우(리더용 셀프) → 부모 없음으로 처리
        parent = sup if (sup and sup in visible_names and sup != emp['name']) else ''
        node = _make_node(emp, parent)
        nodes.append(node)
        id_map[emp['name']] = node

    # 게임베리스튜디오·뉴플레이: 임형철을 최상위로 추가하고 고아 노드 연결
    if filter_corp in ('게임베리스튜디오', '뉴플레이'):
        _ensure_im_hyeongcheol(nodes, id_map, employees)

    # 게임베리스튜디오: 블랙/골든/레드 팀 헤더 가상 노드
    if filter_corp == '게임베리스튜디오':
        _inject_gb_structure(nodes, id_map)

    # 에임드: UA팀·AI개발팀·각 팀 헤더 가상 노드 → DFS 정렬
    if filter_corp == '에임드':
        _inject_ua_structure(nodes, id_map)
        _inject_ai_vacancy(nodes, id_map)
        _inject_game_ops_vacancy(nodes, id_map)
        _inject_aimed_team_headers(nodes, id_map)
        nodes = _sort_dfs(nodes, _AIMED_ORDER_MAP)

    # 마티니: COO 구조 + 4개 팀 + CRM/BA 파트
    if filter_corp == '마티니':
        _inject_martini_structure(nodes, id_map)

    # 뉴플레이: 팀 헤더 가상 노드
    if filter_corp == '뉴플레이':
        _inject_newplay_structure(nodes, id_map)

    return nodes
