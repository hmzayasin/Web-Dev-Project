/* F5: live filtering on /jobs. Progressive enhancement: without JavaScript the
   form still works because it submits to the server (main.jobs). */
(function () {
  var form = document.getElementById('job-filters');
  var list = document.getElementById('job-list');
  if (!form || !list) return;

  var cards = Array.prototype.slice.call(list.querySelectorAll('.job'));
  var count = document.getElementById('job-count');
  var empty = document.getElementById('job-empty');
  var q = form.elements['q'], loc = form.elements['location'],
      type = form.elements['type'], sort = form.elements['sort'];

  function norm(s) { return (s || '').toLowerCase().trim(); }

  function matches(card, words, l, t) {
    var hay = card.getAttribute('data-search') || '';
    for (var i = 0; i < words.length; i++) { if (hay.indexOf(words[i]) === -1) return false; }
    if (l && card.getAttribute('data-location') !== l) return false;
    if (t && card.getAttribute('data-type') !== t) return false;
    return true;
  }

  function order(a, b) {
    var byIndex = a.getAttribute('data-index') - b.getAttribute('data-index');
    if (sort.value === 'closing') {
      var ca = a.getAttribute('data-closing'), cb = b.getAttribute('data-closing');
      if (ca !== cb) return ca < cb ? -1 : 1;
    } else {
      var na = a.getAttribute('data-created'), nb = b.getAttribute('data-created');
      if (na !== nb) return na < nb ? 1 : -1;
    }
    return byIndex;
  }

  function apply() {
    var words = norm(q.value).split(/\s+/).filter(Boolean);
    var l = norm(loc.value), t = norm(type.value), shown = 0;
    cards.sort(order).forEach(function (card) {
      var ok = matches(card, words, l, t);
      card.hidden = !ok;
      if (ok) shown++;
      list.appendChild(card);
    });
    count.textContent = shown + (shown === 1 ? ' opportunity' : ' opportunities');
    empty.hidden = shown !== 0;

    // keep the address bar shareable / refresh-safe
    var params = [];
    if (q.value.trim()) params.push('q=' + encodeURIComponent(q.value.trim()));
    if (loc.value) params.push('location=' + encodeURIComponent(loc.value));
    if (type.value) params.push('type=' + encodeURIComponent(type.value));
    if (sort.value !== 'newest') params.push('sort=' + encodeURIComponent(sort.value));
    if (window.history && history.replaceState) {
      history.replaceState(null, '', location.pathname + (params.length ? '?' + params.join('&') : ''));
    }
  }

  form.addEventListener('submit', function (e) { e.preventDefault(); apply(); });
  q.addEventListener('input', apply);
  [loc, type, sort].forEach(function (el) { el.addEventListener('change', apply); });
  apply();
})();
