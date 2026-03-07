from __future__ import annotations


def build_dashboard_html(*, title: str, token: str) -> str:
    safe_title = (title or "GOC Issue Dashboard").replace("<", "").replace(">", "")
    safe_token = (token or "").replace('"', "").replace("<", "").replace(">", "")
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    :root {{
      --bg: #f4f7f8;
      --ink: #12222b;
      --muted: #60727f;
      --card: #ffffff;
      --line: #d9e2e7;
      --brand: #0a6e8f;
      --brand2: #0f8f68;
      --warn: #c3432d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: radial-gradient(circle at 15% 10%, #eaf4f8 0%, var(--bg) 50%);
      font-family: "Pretendard", "Noto Sans KR", sans-serif;
    }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
    .top {{
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 16px;
    }}
    .top h1 {{ margin: 0; font-size: 24px; letter-spacing: -0.2px; }}
    .token {{ color: var(--muted); font-size: 12px; }}
    .grid {{
      display: grid; gap: 12px;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      margin-bottom: 12px;
    }}
    .kpi {{
      background: var(--card); border: 1px solid var(--line); border-radius: 12px;
      padding: 14px;
    }}
    .kpi .k {{ font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
    .kpi .v {{ font-size: 26px; font-weight: 700; }}
    .panel {{
      background: var(--card); border: 1px solid var(--line); border-radius: 12px;
      padding: 14px;
    }}
    .filters {{
      display: grid; gap: 8px; margin-bottom: 10px;
      grid-template-columns: 1.1fr 0.8fr 0.8fr 0.8fr 1fr auto auto auto;
    }}
    select, input, button {{
      height: 36px; border-radius: 8px; border: 1px solid var(--line); padding: 0 10px;
      background: #fff; color: var(--ink);
    }}
    button {{
      border: none; cursor: pointer; font-weight: 600; background: var(--brand); color: #fff;
    }}
    button.alt {{ background: var(--brand2); }}
    button.warn {{ background: var(--warn); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px; text-align: left; font-size: 13px; }}
    th {{ color: var(--muted); font-weight: 600; }}
    .pager {{ margin-top: 10px; display: flex; justify-content: space-between; align-items: center; }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 980px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .filters {{ grid-template-columns: 1fr 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <h1>{safe_title}</h1>
      <div class="token" id="tokenView"></div>
    </div>

    <div class="grid">
      <div class="kpi"><div class="k">Open Total</div><div class="v" id="kOpen">-</div></div>
      <div class="kpi"><div class="k">Overdue</div><div class="v" id="kOverdue">-</div></div>
      <div class="kpi"><div class="k">Due 7 Days</div><div class="v" id="kDue7">-</div></div>
      <div class="kpi"><div class="k">Watchrooms</div><div class="v" id="kRooms">-</div></div>
    </div>

    <div class="panel" style="margin-bottom:12px;">
      <div class="filters">
        <select id="roomSelect"><option value="">전체 방</option></select>
        <select id="statusSelect">
          <option value="OPEN">OPEN</option>
          <option value="ALL">ALL</option>
          <option value="CLOSED">CLOSED</option>
        </select>
        <input id="ownerInput" placeholder="담당자 필터" />
        <input id="qInput" placeholder="제목/내용 검색" />
        <button id="btnSearch">조회</button>
        <button class="alt" id="btnIssueSummary">이슈요약 푸시</button>
        <button class="warn" id="btnWarn">워닝 푸시</button>
        <button id="btnRefresh">새로고침</button>
      </div>
      <div id="msg" class="muted"></div>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>ID</th><th>상태</th><th>제목</th><th>담당</th><th>목표일</th><th>D-Day</th><th>Age</th><th>방</th>
          </tr>
        </thead>
        <tbody id="tb"></tbody>
      </table>
      <div class="pager">
        <div id="pageInfo" class="muted">-</div>
        <div>
          <button id="btnPrev">이전</button>
          <button id="btnNext">다음</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    const urlToken = new URLSearchParams(location.search).get("token") || "{safe_token}";
    const state = {{ page: 0, size: 30, total: 0 }};
    const $ = (id) => document.getElementById(id);
    $("tokenView").textContent = urlToken ? "token connected" : "token missing";

    function api(path) {{
      const sep = path.includes("?") ? "&" : "?";
      return fetch(`${{path}}${{sep}}token=${{encodeURIComponent(urlToken)}}`).then(r => r.json());
    }}

    function esc(s) {{
      return String(s ?? "").replace(/[&<>"']/g, c => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[c]));
    }}

    async function loadRooms() {{
      const data = await api("/api/watchrooms");
      const sel = $("roomSelect");
      const cur = sel.value;
      sel.innerHTML = '<option value="">전체 방</option>';
      for (const r of (data.items || [])) {{
        const opt = document.createElement("option");
        opt.value = r.room_id;
        opt.textContent = `${{r.room_id}} ${{r.chatroom_title ? "(" + r.chatroom_title + ")" : ""}}`;
        sel.appendChild(opt);
      }}
      sel.value = cur;
    }}

    async function loadSummary() {{
      const data = await api("/api/dashboard/summary");
      const k = (data.kpi || {{}});
      $("kOpen").textContent = k.open_total ?? 0;
      $("kOverdue").textContent = k.overdue ?? 0;
      $("kDue7").textContent = k.due_7 ?? 0;
      $("kRooms").textContent = k.watchrooms ?? 0;
    }}

    async function loadIssues() {{
      const room = $("roomSelect").value;
      const status = $("statusSelect").value;
      const owner = $("ownerInput").value.trim();
      const q = $("qInput").value.trim();
      const p = state.page;
      const s = state.size;
      const qs = new URLSearchParams({{ room_id: room, status, owner, q, page: String(p), size: String(s) }});
      const data = await api(`/api/dashboard/issues?${{qs.toString()}}`);
      const items = data.items || [];
      state.total = Number(data.total || 0);
      const tb = $("tb");
      tb.innerHTML = items.map(it => `
        <tr>
          <td>${{esc(it.issue_id)}}</td>
          <td>${{esc(it.status)}}</td>
          <td>${{esc(it.title)}}</td>
          <td>${{esc(it.owner)}}</td>
          <td>${{esc(it.target_date)}}</td>
          <td>${{esc(it.d_day)}}</td>
          <td>${{esc(it.age_days)}}</td>
          <td>${{esc(it.scope_room_id)}}</td>
        </tr>
      `).join("");
      const from = state.total === 0 ? 0 : p * s + 1;
      const to = Math.min((p + 1) * s, state.total);
      $("pageInfo").textContent = `${{from}}-${{to}} / ${{state.total}}`;
    }}

    async function runJob(path, okMsg) {{
      try {{
        const data = await fetch(`${{path}}?token=${{encodeURIComponent(urlToken)}}`, {{ method: "POST" }}).then(r => r.json());
        $("msg").textContent = data.ok ? okMsg : (data.error || "실패");
      }} catch (e) {{
        $("msg").textContent = "요청 실패: " + e;
      }}
    }}

    $("btnSearch").onclick = async () => {{ state.page = 0; await loadIssues(); }};
    $("btnRefresh").onclick = async () => {{ await loadRooms(); await loadSummary(); await loadIssues(); }};
    $("btnPrev").onclick = async () => {{ if (state.page > 0) {{ state.page -= 1; await loadIssues(); }} }};
    $("btnNext").onclick = async () => {{
      if ((state.page + 1) * state.size < state.total) {{
        state.page += 1;
        await loadIssues();
      }}
    }};
    $("btnIssueSummary").onclick = async () => runJob("/api/jobs/run_issue_summary", "이슈요약 푸시 실행 완료");
    $("btnWarn").onclick = async () => runJob("/api/jobs/run_warn", "워닝 푸시 실행 완료");

    (async () => {{
      await loadRooms();
      await loadSummary();
      await loadIssues();
    }})();
  </script>
</body>
</html>"""
