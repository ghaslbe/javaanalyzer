"""HTML templates for the browsable search UI in server.py.

Kept separate from server.py so the routing stays readable. Uses Jinja
macros (via Flask's render_template_string) so the same "occurrence card"
markup is shared between the search page, the lazy-loaded caller fragment,
and could be reused elsewhere later.

No JS framework, no CDN, no build step -- a few dozen lines of vanilla JS
for the "expand to see who calls this" drill-down, everything else is
plain HTML via <details>/<summary>.
"""

STYLE = """
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, "Segoe UI", Arial, sans-serif; max-width: 920px;
         margin: 2rem auto; padding: 0 1rem; line-height: 1.45; }
  a { color: #2a6ebb; }
  form.search { display: flex; gap: .5rem; margin-bottom: 1.5rem; }
  form.search input[type=text] { flex: 1; font-size: 1.1rem; padding: .5rem .75rem;
         border: 1px solid #888; border-radius: 6px; }
  form.search button { font-size: 1.1rem; padding: .5rem 1.1rem; border-radius: 6px;
         border: 1px solid #888; cursor: pointer; background: rgba(128,128,128,.12); }
  .count { color: #888; font-size: .9rem; margin-bottom: 1rem; }
  .result { border: 1px solid rgba(128,128,128,.35); border-radius: 8px;
         padding: .75rem 1rem; margin-bottom: 1rem; }
  .head { font-size: 1.05rem; }
  .head a.cls { font-weight: 600; text-decoration: none; }
  .head a.cls:hover { text-decoration: underline; }
  .head .mth { color: #666; }
  .meta { font-size: .85rem; color: #777; margin: .15rem 0 .5rem; }
  pre.code { background: rgba(128,128,128,.08); border-radius: 6px; padding: .5rem .75rem;
         overflow-x: auto; font-size: .82rem; margin: 0; }
  pre.code .hl { display: inline-block; width: 100%; background: rgba(255,200,0,.28); font-weight: 600; }
  details.used-by { margin-top: .6rem; padding-left: .9rem; border-left: 2px solid rgba(128,128,128,.3); }
  details.used-by > summary { cursor: pointer; color: #555; font-size: .9rem; }
  details.used-by .used-by-content { margin-top: .5rem; }
  .empty { color: #888; font-style: italic; }
  h2 { word-break: break-all; }
  ul.plain { padding-left: 1.1rem; }
</style>
"""

SCRIPT = """
<script>
function toggleCallers(details) {
  if (details.dataset.loaded === "true") return;
  var box = details.querySelector(".used-by-content");
  var key = details.dataset.method;
  box.innerHTML = '<p class="empty">lade...</p>';
  fetch("/fragment/callers?method=" + encodeURIComponent(key) + "&context=3")
    .then(function (r) { return r.text(); })
    .then(function (html) { box.innerHTML = html; details.dataset.loaded = "true"; })
    .catch(function () { box.innerHTML = '<p class="empty">Fehler beim Laden.</p>'; });
}
</script>
"""

# {{ occ.class }} links to the class detail page; occ.method (a signature
# string) has no link target of its own. Every occurrence -- the main hit
# or a caller several levels deep -- renders through this one macro.
OCCURRENCE_MACRO = """
{% macro occurrence_card(occ) %}
<div class="result">
  <div class="head">
    {% if occ.class %}<a class="cls" href="{{ url_for('type_page', fqn=occ.class) }}">{{ occ.class }}</a>{% if occ.method %}<span class="mth">#{{ occ.method }}</span>{% endif %}
    {% else %}<span class="mth">{{ occ.path.replace('\\\\', '/').rsplit('/', 1)[-1] }}</span>
    {% endif %}
  </div>
  <div class="meta">{% if occ.package %}{{ occ.package }} &middot; {% endif %}{{ occ.path }}:{{ occ.line }}</div>
  <pre class="code">{% for row in occ.code %}<span class="{{ 'hl' if row.line == occ.line else '' }}">{{ '%5d'|format(row.line) }}  {{ row.text }}</span>
{% endfor %}</pre>
</div>
{% endmacro %}
"""

# loaded=true renders used_by right away (already fetched server-side, e.g.
# the first level of a search hit). loaded=false renders a collapsed,
# empty placeholder that lazy-fetches its content on first expand (via
# toggleCallers() -> GET /fragment/callers) -- this is what makes "click
# ever deeper" work without pre-computing the whole call tree up front.
USED_BY_MACRO = """
{% macro used_by_block(used_by, key, loaded) %}
{% if key %}
<details class="used-by" data-method="{{ key }}" data-loaded="{{ 'true' if loaded else 'false' }}"
          ontoggle="if(this.open) toggleCallers(this)">
  <summary>genutzt von{% if loaded %} ({{ used_by|length }}){% endif %}</summary>
  <div class="used-by-content">
    {% if loaded %}
      {% if used_by %}
        {% for caller in used_by %}
          {{ occurrence_card(caller) }}
          {{ used_by_block(None, method_key(caller), false) }}
        {% endfor %}
      {% else %}
        <p class="empty">kein Aufrufer im indexierten Repo gefunden</p>
      {% endif %}
    {% endif %}
  </div>
</details>
{% endif %}
{% endmacro %}
"""

SEARCH_PAGE = (
    """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>javaindex Suche</title>
"""
    + STYLE
    + SCRIPT
    + OCCURRENCE_MACRO
    + USED_BY_MACRO
    + """
</head>
<body>
  <h1><a href="/" style="text-decoration:none; color:inherit;">javaindex</a></h1>
  <form class="search" method="get" action="/">
    <input type="text" name="q" value="{{ q }}" placeholder="Klassenname, Methode oder Text suchen..." autofocus>
    <button type="submit">Suchen</button>
  </form>
  {% if q %}
    <div class="count">{{ results|length }} Treffer für &quot;{{ q }}&quot;</div>
    {% if not results %}
      <p class="empty">Keine Treffer.</p>
    {% endif %}
    {% for result in results %}
      {{ occurrence_card(result.occurrence) }}
      {% if result.kind == 'method' %}
        {{ used_by_block(result.used_by, method_key(result.occurrence), true) }}
      {% endif %}
    {% endfor %}
  {% endif %}
</body>
</html>
"""
)

CALLERS_FRAGMENT = (
    OCCURRENCE_MACRO
    + USED_BY_MACRO
    + """
{% if callers %}
  {% for caller in callers %}
    {{ occurrence_card(caller) }}
    {{ used_by_block(None, method_key(caller), false) }}
  {% endfor %}
{% else %}
  <p class="empty">kein Aufrufer im indexierten Repo gefunden</p>
{% endif %}
"""
)

TYPE_PAGE = (
    """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{{ info.fqn }}</title>
"""
    + STYLE
    + """
</head>
<body>
  <p><a href="/">&larr; zur Suche</a></p>
  <h2>{{ info.fqn }}</h2>
  <div class="meta">{{ info.kind }} &middot; {{ info.path }}</div>
  {% if info.superclass_fqn %}
    <p>extends <a href="{{ url_for('type_page', fqn=info.superclass_fqn) }}">{{ info.superclass_fqn }}</a></p>
  {% endif %}
  {% if info.implements %}
    <p>implements
      {% for i in info.implements %}<a href="{{ url_for('type_page', fqn=i) }}">{{ i }}</a>{{ ", " if not loop.last }}{% endfor %}
    </p>
  {% endif %}

  <h3>Felder</h3>
  {% if info.fields %}
    <ul class="plain">{% for f in info.fields %}<li>{{ f.type }} {{ f.name }}</li>{% endfor %}</ul>
  {% else %}<p class="empty">keine</p>{% endif %}

  <h3>Methoden</h3>
  {% if info.methods %}
    <ul class="plain">
      {% for m in info.methods %}
        <li><a href="/?q={{ m.name }}">{{ m.signature }}</a>{% if m.return_type %} : {{ m.return_type }}{% endif %}</li>
      {% endfor %}
    </ul>
  {% else %}<p class="empty">keine</p>{% endif %}
</body>
</html>
"""
)


def method_key(occ):
    """Stable key for an occurrence's enclosing method, used to request its
    callers lazily. None for occurrences without a method (a bare type/file
    hit doesn't have "callers")."""
    if occ.get("method"):
        return f"{occ['class']}#{occ['method']}"
    return None
