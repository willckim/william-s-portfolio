/* Tour Engine, vendored from github.com/willckim/tour-engine at de22e29.
 * Recorder disabled: see tools/vendor_tour.py and TOUR_ENGINE.md. */
/* ── Guided tour engine, v1 ───────────────────────────────────────────────────
 * Walks a person through a task on the real page: a spotlight on the element
 * they need, a ghost cursor that travels to it, and a card saying what to do.
 *
 * Loaded ONLY in the parent document (/manager). Some targets live inside the
 * My Time iframe (/?embed=1), so every target resolves to a descriptor
 *
 *     { el, doc, frameEl }       frameEl is null for a parent-document target
 *
 * and nothing is ever injected into the frame. The engine listens to the
 * frame's document; all drawing happens in the parent.
 *
 * Six rules, each one a bug if broken:
 *
 *  1. Geometry is read in ONE function, rectOf(). An in-frame rect is relative
 *     to the frame's viewport, and a call that forgets the frame offset draws
 *     the spotlight in the wrong place with no error anywhere.
 *  2. Visible means a non-zero translated rect AND, for an in-frame target, a
 *     visible iframe in the parent. The frame's own document cannot see the
 *     parent hiding it.
 *  3. Never expand a collapsed panel. Expanding writes the person's layout
 *     preference, and a tour must not rearrange somebody's dashboard. It asks
 *     them to open it instead.
 *  4. Advance by delegation. The week view rebuilds its day-group toggles with
 *     innerHTML, so a listener on the node is silently lost. One capture-phase
 *     listener per document, and the target is re-resolved on every event.
 *  5. Geometry and selectors only. The tour reads no page content, and the
 *     engine writes to no storage but its own two sessionStorage keys, for a
 *     tour and a recording that cross a page load. Record mode reads the words
 *     on a control, and screens them: see "Record mode".
 *  6. Styles go in through the CSSOM, never as text in the document. No
 *     <style> element and no style attribute, because a host sending
 *     style-src 'self' refuses both, silently. See installStyles().
 *
 * Everything above about /manager, frames, data-tab and day groups is the
 * prototype's. A page that is not the prototype's describes itself through
 * window.TourHost instead, and the engine learns nothing about it any other
 * way. See "The host" below.
 */
(function (global) {
    'use strict';

    /* Read now. document.currentScript names the executing script only while
       it executes, and the <link> fallback finds its stylesheet from it. */
    const SCRIPT = document.currentScript;

    /* The employee page is also what the My Time iframe loads. The engine runs
       on it STANDALONE, so a tour can survive the real page load between
       /manager and /, and does nothing at all inside the frame: no trigger, no
       listeners, no global. Prompt 1's rule kept by construction rather than by
       remembering not to add a script tag. */
    if (global.top !== global.self ||
        document.documentElement.classList.contains('embedded')) return;

    /* ── The tour. Edit here. ──────────────────────────────────────────────────
     * The prototype's own tour. A host page replaces it with TourHost.steps,
     * which take the same fields except frame.
     *
     * sel      CSS selector, resolved in the parent, or in the My Time iframe
     *          when frame is true. The FIRST match is used, as it always has
     *          been, and a sel that matches more than one element is warned
     *          about once in the console. A step gives sel or target, not both.
     * target   a RANKED list of ways to find the one element, tried in order.
     *          The first that matches exactly one element in the step's own
     *          document wins; one that matches none, or several, is skipped:
     *            { by: 'id',    value: 'task-select' }
     *            { by: 'data',  attr: 'data-tab', value: 'week' }
     *            { by: 'label', value: 'Task Type' }     the control it labels
     *            { by: 'text',  value: 'Stop & Save' }   the smallest element
     *                           reading exactly that, icons at either end aside
     *            { by: 'css',   value: '#task-picker select' }
     *          The winner is said in the console for every step, and a step
     *          found by anything but its first way is warned about, so a page
     *          change that the list survived is still visible.
     * kind     'note': a card with nothing to point at, for a browser dialog.
     *          'region': a spotlight on a CONTAINER, read rather than clicked.
     *          No ghost cursor, advance 'next' only. For content, such as the
     *          rows of a day, which no single-element handle survives.
     * advance  'click':  moves on when the person clicks the target itself
     *          'next':   shows a Next button and waits for it
     *          'reveal': no Next button; moves on when `reveals` appears
     * reveals  what the target OPENS, for a control whose click opens a panel
     *          rather than finishing. A 'click' step would move on at the click
     *          and point at a panel that is not there yet, or never comes.
     *          Required for 'reveal'. On a 'next' step it also moves the tour
     *          on by itself once it appears, so a person who does the thing the
     *          card describes is not left holding a chip.
     * keepClear  any control this card talks about besides its own target,
     *          which its card must leave clickable. The target always is.
     * when     what has to be on screen for the step to apply at all, read once
     *          as the step comes up. A step that does not apply is DROPPED, not
     *          waited for: a Stop step for somebody with nothing running would
     *          otherwise wait, then say it could not find Stop.
     * tab      the tab the target lives on. When another tab is showing, the
     *          step is preceded by one pointing at that tab's button. Left off
     *          where the target is on every tab.
     * targetName   what the target IS, for a person: 'the task picker'. Said
     *          on the card when the target cannot be found.
     * instruction  what to do without the highlight: 'Choose your task'. The
     *          card reads "We could not find <targetName>. <instruction>, then
     *          press Continue." Falls back to the title. Describe what a control
     *          does, not the words on it: a label can change under the tour, and
     *          nothing would notice the card now naming a button that is gone.
     */
    /* Every fallback below was checked on the intact app with Playwright's own
       locators: unique in its document, and the same element as the step's
       first way. None of this app's labels is unique ("Task Type" and "Notes
       (optional)" each label several controls), so no step uses one. */
    const STEPS = [
        { target: [{ by: 'css', value: '.tab[data-tab="my-time"]' },
                   { by: 'text', value: 'My Time' }],
          title: 'Open My Time',
          body: 'Your own timer lives on this tab. Click My Time to open it.',
          targetName: 'the My Time tab', instruction: 'Open the My Time tab',
          advance: 'click' },
        { tab: 'my-time', frame: true,
          target: [{ by: 'id', value: 'task-select' },
                   { by: 'css', value: '#task-picker select' }],
          title: 'Choose a task',
          body: 'Pick what you are working on from this list, then press Next.',
          targetName: 'the task picker', instruction: 'Choose your task',
          advance: 'next' },
        { tab: 'my-time', frame: true,
          target: [{ by: 'id', value: 'start-btn' },
                   { by: 'text', value: 'Start Timer' }],
          title: 'Start the timer',
          body: 'Click Start Timer. The clock starts counting straight away.',
          targetName: 'the button that starts the timer', instruction: 'Start the timer',
          advance: 'click' },
        { tab: 'my-time', frame: true,
          target: [{ by: 'id', value: 'notes-input' },
                   { by: 'css', value: '#running-state textarea' }],
          title: 'Add a note if you like',
          body: 'Notes are optional. They are saved with this session when you stop.',
          targetName: 'the notes box', instruction: 'Add a note if you like',
          advance: 'next' },
        { tab: 'my-time', frame: true,
          target: [{ by: 'id', value: 'stop-btn' },
                   { by: 'text', value: 'Stop & Save' },
                   { by: 'css', value: '#running-state .btn-danger' }],
          title: 'Stop and save',
          body: 'When you finish, click Stop and Save. Your time is recorded.',
          targetName: 'the button that stops the timer and saves', instruction: 'Stop the timer and save',
          advance: 'click' },
        { tab: 'my-time', frame: true,
          target: [{ by: 'css', value: '.tab[data-tab="week"]' },
                   { by: 'text', value: 'My Time' }],
          title: 'See your week',
          body: 'Click this My Time tab, inside the page, to see what you logged this week.',
          targetName: 'the My Time tab inside the page', instruction: 'Open the My Time tab inside the page',
          advance: 'click' },
        /* A REGION, not a row. The row step stacked three assumptions on the
           markup (a today-header class, header and body as siblings, table
           rows) and took the first of several matches. The day's group is the
           thing a person looks at, and the whole week list is the coarse
           fallback: the copy holds for both. */
        { tab: 'my-time', frame: true, kind: 'region',
          target: [{ by: 'css', value: '#week-entries .day-group:has(> .day-header.today-header)' },
                   { by: 'id', value: 'week-entries' }],
          title: 'Your entry',
          body: 'Today is at the top of your week. The time you just saved is listed there.',
          targetName: 'your week', instruction: "Look at the top of your week for today's entries",
          advance: 'next' },
    ];

    /* ── What the engine needs to know about this app. ────────────────────── */
    const CONFIG = {
        frameSelector: '#my-time-frame',
        // Before sign-in there is nothing to point at, and a tour started on
        // the login screen would skip every step.
        isReady: function () {
            // The dashboard gates on its own overlay. The employee page has no
            // such element, so a visible tab bar stands in for "there is
            // something here to point at".
            const d = document.getElementById('dashboard');
            if (d) return !d.classList.contains('hidden');
            return !!document.querySelector('.tab');
        },
        // What opens a collapsed container, found by the container's id. Day
        // groups name their body with aria-controls; dashboard sections use
        // data-section-toggle. Both carry aria-expanded.
        controllersFor: function (id) {
            const q = CSS.escape(id);
            return ['[aria-controls="' + q + '"]', '[data-section-toggle="' + q + '"]'];
        },
        tabPanel:  '.tab-panel',
        tabButton: '.tab',
        // My Time is #my-time on /manager and #week on the employee page. A
        // step naming one is satisfied by either, whichever this page has.
        tabAliases: { 'my-time': ['my-time', 'week'] },
        tabPollMs: 500,
        // Namespaced to the tour. Never tt_sections, which is the app's.
        resumeKey: 'tour.resume',
        // A recording under way, so it outlives a page load. The same namespace.
        recordKey: 'tour.record',
        frameTimeoutMs:  3000,
        targetTimeoutMs: 3000,
        maxExpandDepth:  3,
        pad: 6,            // spotlight breathing room around the target
        gap: 12,           // space between the spotlight and the card
    };

    /* ── The host ─────────────────────────────────────────────────────────────
     * A page that is not the prototype's sets this in a script loaded BEFORE
     * this one:
     *
     *   window.TourHost = {
     *     steps:   [ ... ],            REQUIRED. Replaces STEPS.
     *     isReady: function () {},     REQUIRED. True when the page has
     *                                  something to point at.
     *     tabs: {                      Optional. Replaces the data-tab lookup.
     *       current: function () {},       the showing tab's name, or null
     *       button:  function (name) {},   a selector for the control that
     *     },                               opens that tab, or null
     *     collapsedToggle: function (el) {},
     *                                  Optional. Replaces the aria-controls
     *                                  lookup: a selector for the control that
     *                                  unfolds whatever is hiding el, or null
     *                                  when nothing folds it.
     *     keepClear: '<selector>',     Optional. Controls no card on this page
     *                                  may cover, because a person may need to
     *                                  click them while any card is up: the
     *                                  tabs a guide will ask for, for one.
     *     timeouts: {                  Optional, milliseconds.
     *       firstTargetMs: ...,            until this run has shown a target
     *       targetMs: ...,                 every wait after that
     *     },
     *   };
     *
     * AND ON THE ENGINE'S OWN TAG, data-tour-host:
     *
     *   <script src="/js/tour.js" data-tour-host></script>
     *
     * which says this page describes itself. Without it, a page with no
     * TourHost is taken for the prototype and gets the built-in tour, which is
     * exactly what a host gets when its steps file 404s or loads after this
     * one. With it, no TourHost is refused like a malformed one.
     *
     * STEPS AND isReady ARE REQUIRED because the built-in ones describe this
     * prototype: its tour, and its guess at what a signed-in page looks like. A
     * host that left either out would get a tour of a page it is not, or a
     * trigger that never appears, and neither would say anything.
     *
     * CHECKED ONCE, AT MOUNT, AND REFUSED WHOLE. A misspelt key is the same
     * silence as a missing one, because the built-in rule quietly stands in for
     * it. So an unknown key, a wrong type or a selector that does not parse
     * keeps the tour off, and the console names every problem at once.
     *
     * The same goes for a step: a key the engine does not read is refused,
     * because a misspelt tab or advance drops that behaviour and nothing else.
     *
     * Host functions are called as plain functions, with no this. A function
     * that throws is read as "no": not ready, no tab, nothing folded. Said once
     * per function, not on every tick.
     *
     * THE FIRST TARGET GETS THE LONGER WAIT, NOT THE FIRST STEP. A server that
     * scales to zero can take seconds after the page arrives to render what a
     * tour points at, and the person who pressed the button did nothing wrong.
     * The longer allowance lasts until something has been shown in this run,
     * so it also covers a resume after a reload, which starts mid-tour on a
     * page that is just as cold. Once anything has rendered the server is up,
     * and later steps get the ordinary wait.
     *
     * A resume has to wait for isReady before any target can be looked for,
     * so it keeps asking for at least the same allowance. It used to stop at a
     * fixed 15 seconds, and a page slower than that to be ready lost its place
     * with nothing said.
     */
    const HOST_KEYS = ['steps', 'isReady', 'tabs', 'collapsedToggle', 'timeouts', 'keepClear'];
    // frame is listed so it gets its own refusal below, not "unknown key".
    const HOST_STEP_KEYS = ['sel', 'title', 'body', 'advance', 'tab', 'kind', 'after',
                            'reveals', 'when', 'keepClear', 'frame', 'targetName', 'instruction',
                            'target'];
    // The ways a target list may find its element, and the keys each one takes.
    const STRATEGY_KEYS = {
        id:    ['by', 'value'],
        data:  ['by', 'attr', 'value'],
        label: ['by', 'value'],
        text:  ['by', 'value'],
        css:   ['by', 'value'],
    };
    const STEP_KINDS = ['note', 'region'];
    const HOST_TAB_KEYS = ['current', 'button'];
    const HOST_TIMEOUT_KEYS = ['firstTargetMs', 'targetMs'];
    const HOST_MAX_WAIT_MS = 120000;

    let host = null;           // the checked TourHost, or null on the prototype
    let hostRefused = false;   // a TourHost was given and failed its check
    const saidOnce = {};       // host faults already reported

    const UI = 'data-tour-ui';

    let steps     = [];
    let current   = -1;
    let foundBy   = null;      // how the shown step's element was found, for state()
    let active    = false;
    let runToken  = 0;         // bumped on every step change; stale waits give up
    let waitTimer = null;
    let tickTimer = null;
    let frameReq  = 0;
    let ui        = null;      // { spot, cursor, tip }
    let lastCenter = null;     // where the cursor travels from
    let cursorTo  = '';        // the last transform applied, as written
    let travelUntil = 0;       // while travelling, a reposition retargets
    let placedIndex = -1;      // the step place(true) has drawn
    let activeTabName = null;  // the tab the parent page is showing
    let tabErrors  = 0;        // lookups that reached the wrong document
    let timedOut   = false;    // the current step could not be found
    let shownTarget = false;   // this run has put the spotlight on something
    let mounted    = false;    // the trigger exists and the host has been read
    let tourId     = 'default';
    let tabObserver = null;
    let tabPoll    = null;
    let trigger   = null;
    const listening = [];      // documents holding our capture listeners

    function reducedMotion() {
        return !!(global.matchMedia &&
                  global.matchMedia('(prefers-reduced-motion: reduce)').matches);
    }

    /* ── Styles ───────────────────────────────────────────────────────────────
     * The engine installs its own rules, so a host page needs one <script> tag
     * and no <link>.
     *
     * NEVER AS TEXT IN THE DOCUMENT. The Ortho Functions host sends
     * style-src 'self' with no 'unsafe-inline' and no nonce, which refuses an
     * injected <style> element (inside a shadow root too), a style attribute,
     * and either one carried by innerHTML. Refused silently: the overlay just
     * draws unstyled. What that policy allows, measured in Chromium, is the
     * CSSOM: el.style writes, which is how every position here is set, and a
     * constructable sheet adopted by the document, which is how the rules are.
     *
     * A browser without constructable sheets gets a same-origin <link> to
     * tour.css, which the same policy allows. Its href is the script tag's
     * data-tour-stylesheet when a host keeps scripts and styles in different
     * folders, as the Ortho host does (/js and /css), and otherwise tour.css
     * beside this file.
     *
     * The adopted text is tour.css itself, embedded verbatim at the end of this
     * file by scripts/sync_tour_css.py, so the two paths apply the same rules.
     * tests/check_tour_csp.py compares both against tour.css parsed through a
     * plain <link>, property by property.
     */
    let stylesReady   = false;
    let stylesFailed  = false;
    let whenStyled    = null;      // one install per page, however often asked
    let deferredStart = null;      // the latest start() that arrived before the rules

    function constructableSheets() {
        if (!('adoptedStyleSheets' in Document.prototype)) return false;
        try { new CSSStyleSheet().replaceSync(''); return true; }
        catch (e) { return false; }     // an older engine with the name and no constructor
    }

    /* The attribute AS WRITTEN, not the resolved .src, so a relative path stays
       relative to the document exactly as the script's own did. A src that does
       not end in tour.js has no sibling to guess, and guessing would link the
       script itself as a stylesheet. */
    function stylesheetHref() {
        if (!SCRIPT) return null;
        const declared = SCRIPT.getAttribute('data-tour-stylesheet');
        if (declared) return declared;
        const src = SCRIPT.getAttribute('src') || '';
        return /tour\.js(?:[?#].*)?$/.test(src)
            ? src.replace(/tour\.js(?:[?#].*)?$/, 'tour.css')
            : null;
    }

    function installStyles() {
        if (whenStyled) return whenStyled;

        if (constructableSheets()) {
            const sheet = new CSSStyleSheet();
            sheet.replaceSync(tourCss());
            // APPENDED, never assigned. A fresh array would drop every sheet the
            // host page adopted for itself.
            document.adoptedStyleSheets =
                Array.prototype.slice.call(document.adoptedStyleSheets).concat([sheet]);
            stylesReady = true;
            whenStyled = Promise.resolve(true);
            return whenStyled;
        }

        whenStyled = new Promise(function (done) {
            const href = stylesheetHref();
            if (!href) {
                stylesFailed = true;
                console.error('[tour] no constructable stylesheets and no tour.css to link: '
                            + 'set data-tour-stylesheet on the tour.js script tag');
                return done(false);
            }
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = href;
            link.setAttribute('data-tour-styles', '');
            link.addEventListener('load', function () { stylesReady = true; done(true); });
            link.addEventListener('error', function () {
                stylesFailed = true;
                console.error('[tour] ' + href + ' did not load, so the tour stays off '
                            + 'rather than drawing unstyled');
                done(false);
            });
            document.head.appendChild(link);
        });
        return whenStyled;
    }

    /* ── Reading the host ─────────────────────────────────────────────────────
     * The contract is written out under "The host" above. */
    function sayOnce(key, message) {
        if (saidOnce[key]) return;
        saidOnce[key] = true;
        console.error('[tour] ' + message);
    }

    // The same, for something that works but is fragile rather than wrong.
    function warnOnce(key, message) {
        if (saidOnce[key]) return;
        saidOnce[key] = true;
        console.warn('[tour] ' + message);
    }

    /* Parsed against a detached fragment, so checking a selector never matches
       anything on the page and a bad one throws here rather than mid-tour. */
    function isSelector(s) {
        if (typeof s !== 'string' || !s.trim()) return false;
        try { document.createDocumentFragment().querySelector(s); return true; }
        catch (e) { return false; }
    }

    function unknownKeys(obj, allowed, prefix) {
        return Object.keys(obj)
            .filter(function (k) { return allowed.indexOf(k) === -1; })
            .map(function (k) { return 'unknown key ' + prefix + k; });
    }

    /* opts.frame allows the frame flag, which a host page never has and a
       recording made in this app usually does. Everything else is the same
       rule for both, so a recording is checked exactly as a host's steps are. */
    function stepProblems(list, opts) {
        if (!Array.isArray(list) || !list.length) return ['steps must be a non-empty array'];
        const framed = !!(opts && opts.frame);
        const out = [];
        list.forEach(function (s, i) {
            const at = 'steps[' + i + ']';
            if (!s || typeof s !== 'object') { out.push(at + ' is not an object'); return; }
            out.push.apply(out, unknownKeys(s, HOST_STEP_KEYS, at + '.'));
            if (s.frame && !framed) out.push(at + '.frame: the engine knows no frame on a host page');
            if (s.tab !== undefined && (typeof s.tab !== 'string' || !s.tab)) {
                out.push(at + '.tab must be a tab name');
            }
            ['after', 'when', 'reveals', 'keepClear'].forEach(function (k) {
                if (s[k] !== undefined && !isSelector(s[k])) {
                    out.push(at + '.' + k + ' is not a selector: ' + String(s[k]));
                }
            });
            // Read aloud on a card, so they have to be words.
            ['targetName', 'instruction'].forEach(function (k) {
                if (s[k] !== undefined && (typeof s[k] !== 'string' || !s[k].trim())) {
                    out.push(at + '.' + k + ' must be text a person can read: ' + String(s[k]));
                }
            });
            // A misspelt kind is the same silence as a misspelt key: 'Region'
            // would quietly become an ordinary step with a ghost cursor.
            if (s.kind !== undefined && STEP_KINDS.indexOf(s.kind) === -1) {
                out.push(at + ".kind must be 'note' or 'region': " + String(s.kind));
            }
            if (s.kind === 'note') {
                // A note waits for its own button. A reveals would dismiss it
                // the moment that thing appeared, whether it had been read or not.
                if (s.reveals !== undefined) out.push(at + '.reveals: a note reveals nothing');
                return;
            }
            // One way to name the element, not two that could disagree.
            if (s.sel !== undefined && s.target !== undefined) {
                out.push(at + ': give sel or target, not both');
            } else if (s.sel === undefined && s.target === undefined) {
                out.push(at + ': a step needs sel or target to point at');
            } else if (s.target !== undefined) {
                out.push.apply(out, targetProblems(s.target, at + '.target'));
            } else if (!isSelector(s.sel)) {
                out.push(at + '.sel is not a selector: ' + String(s.sel));
            }
            if (s.kind === 'region') {
                // Read, not clicked: a click would move a region on before the
                // person had looked at it, and a region opens nothing.
                if (s.advance !== 'next') out.push(at + ".advance: a region is read, so advance must be 'next'");
                if (s.reveals !== undefined) out.push(at + '.reveals: a region reveals nothing');
                return;
            }
            if (s.advance !== 'click' && s.advance !== 'next' && s.advance !== 'reveal') {
                out.push(at + ".advance must be 'click', 'next' or 'reveal'");
            }
            if (s.advance === 'reveal' && s.reveals === undefined) {
                out.push(at + ".reveals is required when advance is 'reveal'");
            }
        });
        return out;
    }

    /* Each way of finding the element, checked the way a step is: an unknown
       key or a value that could never match keeps the tour off and is named. */
    function targetProblems(list, at) {
        if (!Array.isArray(list) || !list.length) return [at + ' must be a non-empty list'];
        const out = [];
        list.forEach(function (t, i) {
            const here = at + '[' + i + ']';
            if (!t || typeof t !== 'object' || Array.isArray(t)) { out.push(here + ' is not an object'); return; }
            const keys = STRATEGY_KEYS[t.by];
            if (!keys) {
                out.push(here + ".by must be one of " + Object.keys(STRATEGY_KEYS).join(', ') + ': ' + String(t.by));
                return;
            }
            out.push.apply(out, unknownKeys(t, keys, here + '.'));
            if (typeof t.value !== 'string' || !t.value.trim()) {
                out.push(here + '.value must be non-blank text');
                return;
            }
            if (t.by === 'id' && /[#\s]/.test(t.value)) {
                out.push(here + ".value is an id, with no '#' and no spaces: " + t.value);
            }
            if (t.by === 'data' && !/^data-[a-z0-9][a-z0-9-]*$/.test(String(t.attr))) {
                out.push(here + ".attr must be a data- attribute name: " + String(t.attr));
            }
            if (t.by === 'css' && !isSelector(t.value)) {
                out.push(here + '.value is not a selector: ' + t.value);
            }
        });
        return out;
    }

    function hostProblems(h) {
        if (!h || typeof h !== 'object' || Array.isArray(h)) return ['it must be an object'];
        const out = unknownKeys(h, HOST_KEYS, '').concat(stepProblems(h.steps));
        if (typeof h.isReady !== 'function') out.push('isReady must be a function');
        if (h.tabs !== undefined) {
            if (!h.tabs || typeof h.tabs !== 'object') {
                out.push('tabs must be an object');
            } else {
                out.push.apply(out, unknownKeys(h.tabs, HOST_TAB_KEYS, 'tabs.'));
                HOST_TAB_KEYS.forEach(function (k) {
                    if (typeof h.tabs[k] !== 'function') out.push('tabs.' + k + ' must be a function');
                });
            }
        }
        if (h.collapsedToggle !== undefined && typeof h.collapsedToggle !== 'function') {
            out.push('collapsedToggle must be a function');
        }
        if (h.keepClear !== undefined && !isSelector(h.keepClear)) {
            out.push('keepClear is not a selector: ' + String(h.keepClear));
        }
        if (h.timeouts !== undefined) {
            if (!h.timeouts || typeof h.timeouts !== 'object') {
                out.push('timeouts must be an object');
            } else {
                out.push.apply(out, unknownKeys(h.timeouts, HOST_TIMEOUT_KEYS, 'timeouts.'));
                HOST_TIMEOUT_KEYS.forEach(function (k) {
                    const v = h.timeouts[k];
                    if (v !== undefined && !(typeof v === 'number' && isFinite(v)
                                             && v > 0 && v <= HOST_MAX_WAIT_MS)) {
                        out.push('timeouts.' + k + ' must be a number of milliseconds from 1 to '
                                 + HOST_MAX_WAIT_MS + ', not ' + String(v));
                    }
                });
            }
        }
        return out;
    }

    /* Copied, so a page that changes window.TourHost later does not change a
       tour that was checked against what it said at mount. */
    function readHost() {
        const h = global.TourHost;
        if (h === undefined) {
            // Unmarked, this is the prototype, and the built-in tour is right.
            if (!(SCRIPT && SCRIPT.hasAttribute('data-tour-host'))) return true;
            hostRefused = true;
            console.error('[tour] TourHost refused, so the tour stays off: this page\'s script '
                        + 'tag says data-tour-host and no TourHost was defined. Did the '
                        + 'steps file load, and before tour.js?');
            return false;
        }
        const problems = hostProblems(h);
        if (problems.length) {
            hostRefused = true;
            console.error('[tour] TourHost refused, so the tour stays off: ' + problems.join('; '));
            return false;
        }
        host = {
            steps: h.steps.map(function (s) { return Object.assign({}, s); }),
            isReady: h.isReady,
            tabs: h.tabs ? { current: h.tabs.current, button: h.tabs.button } : null,
            collapsedToggle: h.collapsedToggle || null,
            keepClear: h.keepClear || null,
            timeouts: Object.assign({}, h.timeouts),
        };
        return true;
    }

    function askHost(name, fn, args, fallback) {
        try { return fn.apply(null, args); }
        catch (e) {
            sayOnce('threw:' + name, 'TourHost.' + name + ' threw, so it is read as no: '
                                    + (e && e.message ? e.message : String(e)));
            return fallback;
        }
    }

    function ready() {
        if (hostRefused) return false;
        return host ? !!askHost('isReady', host.isReady, [], false) : CONFIG.isReady();
    }

    /* How long the current step's target may take to appear. See "The host". */
    function targetWaitMs() {
        const t = host ? host.timeouts : {};
        const later = t.targetMs || CONFIG.targetTimeoutMs;
        return shownTarget ? later : (t.firstTargetMs || later);
    }

    /* ── Tabs, without hashchange ─────────────────────────────────────────────
     * A tab click rewrites the hash with replaceState, which fires no
     * hashchange: measured, zero events on a click and one when the hash is set
     * from outside. So the panels are watched instead, and a poll catches any
     * route the observer misses.
     *
     * EVERY TAB LOOKUP IS PARENT-ONLY. The frame has .tab and .tab-panel
     * elements of its own and one of its tabs is ALSO labelled "My Time", so a
     * lookup that reached into it would highlight the wrong document's tab and
     * look almost right. Anything foreign is refused loudly rather than used.
     */
    function parentOnly(nodes, where) {
        const out = [];
        for (let i = 0; i < nodes.length; i++) {
            if (nodes[i].ownerDocument === document) {
                out.push(nodes[i]);
            } else {
                tabErrors++;
                console.error('[tour] ' + where + ' reached outside the parent '
                            + 'document; refusing that element');
            }
        }
        return out;
    }

    function tabPanels() {
        return parentOnly(document.querySelectorAll(CONFIG.tabPanel), 'tab panel lookup');
    }

    function currentTab() {
        if (host && host.tabs) {
            const name = askHost('tabs.current', host.tabs.current, [], null);
            return typeof name === 'string' && name ? name : null;
        }
        const panels = tabPanels();
        for (let i = 0; i < panels.length; i++) {
            if (!panels[i].classList.contains('hidden')
                && styleOf(panels[i]).display !== 'none') {
                return panels[i].dataset.tab || null;
            }
        }
        return null;
    }

    function syncTab() {
        const now = currentTab();
        if (now === activeTabName) return;
        activeTabName = now;
        if (active) schedule();          // a step waiting on a tab may be free
    }

    /* A host's tabs are asked on the poll alone: the engine cannot know which
       elements they are, so there is nothing to observe. A tab guide still
       advances the moment its button is clicked, through onClick. */
    function watchTabs() {
        if (tabObserver || tabPoll) return;
        if (!(host && host.tabs)) {
            tabObserver = new MutationObserver(syncTab);
            tabPanels().forEach(function (p) {
                tabObserver.observe(p, { attributes: true,
                                         attributeFilter: ['class', 'style'] });
            });
        }
        tabPoll = setInterval(syncTab, CONFIG.tabPollMs);
        syncTab();
    }

    // The aliases are the prototype's. A host names its own tabs.
    function tabNames(stepTab) {
        if (host && host.tabs) return [stepTab];
        return CONFIG.tabAliases[stepTab] || [stepTab];
    }

    function tabIsActive(stepTab) {
        return tabNames(stepTab).indexOf(activeTabName) !== -1;
    }

    /* The button that opens this step's tab ON THIS PAGE, or null when the page
       has no such tab at all. */
    function tabButtonFor(stepTab) {
        if (host && host.tabs) {
            const sel = askHost('tabs.button', host.tabs.button, [stepTab], null);
            if (sel === null || sel === undefined) return null;
            if (!isSelector(sel)) {
                sayOnce('tabs.button:' + String(sel), 'TourHost.tabs.button returned '
                        + String(sel) + ' for ' + stepTab + ', which is not a selector');
                return null;
            }
            // Matching nothing is not a fault: the tab is on another page.
            return document.querySelector(sel) ? sel : null;
        }
        const names = tabNames(stepTab);
        for (let i = 0; i < names.length; i++) {
            const sel = CONFIG.tabButton + '[data-tab="' + CSS.escape(names[i]) + '"]';
            if (parentOnly(document.querySelectorAll(sel), 'tab button lookup').length) {
                return sel;
            }
        }
        return null;
    }

    /* ── Resume ───────────────────────────────────────────────────────────────
     * Written on every step rather than only before a click that navigates,
     * which covers the reload case with the same line and means there is no
     * list of "navigating clicks" to keep correct. sessionStorage only, and
     * only this key.
     *
     * THE PLACE IN THE TOUR AS WRITTEN, not in the working list. Guides and
     * "open this first" steps are inserted into that list and steps that do
     * not apply are dropped from it, and a reload starts again from the tour
     * as written. Saving the list position resumed one step late for every
     * insertion, and past the end of the list ended the tour. */
    function saveResume(index) {
        const s = steps[index];
        const at = s && typeof s.origin === 'number' ? s.origin : index;
        try {
            sessionStorage.setItem(CONFIG.resumeKey,
                                   JSON.stringify({ id: tourId, index: at }));
        } catch (e) { /* blocked: the tour simply will not resume */ }
    }

    function clearResume() {
        try { sessionStorage.removeItem(CONFIG.resumeKey); } catch (e) { /* as above */ }
    }

    function pendingResume() {
        let saved = null;
        try { saved = JSON.parse(sessionStorage.getItem(CONFIG.resumeKey) || 'null'); }
        catch (e) { return null; }
        if (!saved || saved.id !== 'default' || typeof saved.index !== 'number') return null;
        return saved.index;
    }

    /* ── Geometry: the ONLY place a rect is read. ─────────────────────────────
     * Returns the element's box in PARENT viewport coordinates. For an in-frame
     * target that means the frame's own box plus its border, because the
     * content box starts inside the border. The frame here has border:0 today,
     * which is exactly when leaving the border out would look correct and then
     * break the day somebody styles it. */
    function rectOf(desc) {
        if (!desc || !desc.el || !desc.el.isConnected) return null;
        const r = desc.el.getBoundingClientRect();
        let dx = 0, dy = 0;
        if (desc.frameEl) {
            if (!desc.frameEl.isConnected) return null;
            const f = desc.frameEl.getBoundingClientRect();
            dx = f.left + desc.frameEl.clientLeft;
            dy = f.top  + desc.frameEl.clientTop;
        }
        return { left: r.left + dx, top: r.top + dy,
                 width: r.width, height: r.height,
                 right: r.right + dx, bottom: r.bottom + dy };
    }

    function centerOf(r) {
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }

    function styleOf(el) {
        // The element's OWN window. A frame element's styles belong to the
        // frame's realm.
        return el.ownerDocument.defaultView.getComputedStyle(el);
    }

    /* ── Visibility ───────────────────────────────────────────────────────────
     * 1. The translated rect has width and height. display:none anywhere above
     *    the element, in either document, collapses it to 0x0.
     * 2. For an in-frame target, the iframe passes the same check in the
     *    PARENT. A parent can hide the frame with visibility:hidden, which
     *    leaves every rect inside it intact and is invisible to the frame's
     *    own document.
     * The element's own visibility is checked too, because a rect survives
     * visibility:hidden. It inherits, so one element's value covers its whole
     * ancestor chain within that document. */
    function isVisible(desc) {
        const r = rectOf(desc);
        if (!r || r.width <= 0 || r.height <= 0) return false;
        if (styleOf(desc.el).visibility === 'hidden') return false;
        if (desc.frameEl) {
            return isVisible({ el: desc.frameEl, doc: document, frameEl: null });
        }
        return true;
    }

    /* ── Resolution ───────────────────────────────────────────────────────── */
    function frameReady() {
        const frameEl = document.querySelector(CONFIG.frameSelector);
        // src is blank until the tab is first opened: the dashboard loads the
        // frame on demand, so a blank src is "not yet", not "broken".
        if (!frameEl || !frameEl.getAttribute('src')) return null;
        let doc = null;
        try { doc = frameEl.contentDocument; } catch (e) { return null; }
        if (!doc || doc.URL === 'about:blank' || doc.readyState === 'loading') return null;
        return { frameEl: frameEl, doc: doc };
    }

    /* ── Finding a step's element ─────────────────────────────────────────────
     * THE DOCUMENT IS DECIDED FIRST, from the step's frame flag, and only that
     * document is searched. Not a filter applied afterwards: the parent and the
     * My Time frame each have a tab reading "My Time", each unique in its own
     * document, so a text search across both would find the wrong one as
     * confidently as the right one. Host pages have no frame, so for a host this
     * is always the page itself.
     */
    function scopeOf(step) {
        if (!step.frame) return { doc: document, frameEl: null };
        const f = frameReady();
        if (!f) return null;
        listenTo(f.doc);          // a reloaded frame is a new document
        return { doc: f.doc, frameEl: f.frameEl };
    }

    function resolve(step) {
        const scope = scopeOf(step);
        if (!scope) return null;
        if (step.target) {
            for (let i = 0; i < step.target.length; i++) {
                const found = matchesOf(scope.doc, step.target[i]);
                if (found.length === 1) {
                    return { el: found[0], doc: scope.doc, frameEl: scope.frameEl, via: i };
                }
            }
            return null;
        }
        /* sel keeps the meaning every existing step was written against: the
           first match. Making it exactly-one would turn a live host step that
           relies on the first of several into a could-not-find card the day its
           build picked up this engine. The first-of-many is made visible instead. */
        const all = scope.doc.querySelectorAll(step.sel);
        if (!all.length) return null;
        if (all.length > 1) {
            warnOnce('many:' + step.sel, step.sel + ' matches ' + all.length
                     + ' elements; the first is used. A target list needs exactly one.');
        }
        return { el: all[0], doc: scope.doc, frameEl: scope.frameEl, via: -1 };
    }

    function quoted(v) {
        return '"' + String(v).replace(/["\\]/g, '\\$&') + '"';
    }

    /* Text as a person reads it: whitespace collapsed, and icon glyphs or
       punctuation at either end let go, so a play icon before "Start Timer"
       still reads 'Start Timer'. */
    function readable(s) {
        return String(s || '').replace(/\s+/g, ' ').trim()
            .replace(/^[^\p{L}\p{N}]+/u, '').replace(/[^\p{L}\p{N}]+$/u, '');
    }

    /* Every element one way of finding matches in this document. A way that
       cannot be evaluated matches nothing, never everything. */
    function matchesOf(doc, t) {
        try {
            if (t.by === 'id') return Array.prototype.slice.call(doc.querySelectorAll('[id=' + quoted(t.value) + ']'));
            if (t.by === 'data') return Array.prototype.slice.call(doc.querySelectorAll('[' + t.attr + '=' + quoted(t.value) + ']'));
            if (t.by === 'css') return Array.prototype.slice.call(doc.querySelectorAll(t.value));
            if (t.by === 'label') return byLabel(doc, readable(t.value));
            if (t.by === 'text') return byText(doc, readable(t.value));
        } catch (e) { /* no match */ }
        return [];
    }

    // The CONTROLS labelled, not the labels: a click on a label is not a click
    // on its control as far as a click step is concerned.
    function byLabel(doc, want) {
        const out = [];
        Array.prototype.forEach.call(doc.querySelectorAll('label'), function (l) {
            const c = l.control;
            if (c && readable(l.textContent) === want && out.indexOf(c) === -1) out.push(c);
        });
        return out;
    }

    /* The OUTERMOST element that reads exactly this and nothing more. A span
       inside a button reading "Stop & Save" gives the button, so a click on its
       padding still counts; the card around the button reads more, so it never
       qualifies. Two separate elements reading the same text are two matches,
       and the way is skipped. The tour's own card and trigger are never
       candidates. */
    function byText(doc, want) {
        if (!want || !doc.body) return [];
        const first = want.split(' ')[0];
        const hits = [];
        const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
            if (n.data.indexOf(first) === -1 || !n.parentElement) continue;
            if (n.parentElement.closest('[' + UI + '], [data-tour-trigger], script, style')) continue;
            let best = null;
            for (let el = n.parentElement, up = 0; el && el !== doc.body && up < 6; el = el.parentElement, up++) {
                const text = readable(el.textContent);
                if (text === want) best = el;
                else if (text.length > want.length) break;     // containers only read more
            }
            if (best && hits.indexOf(best) === -1) hits.push(best);
        }
        return hits.filter(function (el) {
            return !hits.some(function (other) { return other !== el && other.contains(el); });
        });
    }

    function describeWay(t) {
        if (t.by === 'id') return '#' + t.value;
        if (t.by === 'data') return '[' + t.attr + '=' + quoted(t.value) + ']';
        if (t.by === 'css') return t.value;
        return t.by + ' ' + quoted(t.value);
    }

    // What a step points at, in one line: its sel, or its first way.
    function describeTarget(step) {
        if (!step) return null;
        if (step.sel) return step.sel;
        return step.target && step.target.length ? describeWay(step.target[0]) : null;
    }

    function describeAllWays(step) {
        return step.target ? step.target.map(describeWay).join(' | ') : String(step.sel);
    }

    /* The toggle that would open a collapsed container around this target, or
       null. Collapsed is read off aria-expanded, never off styles: it is the
       one signal both collapse mechanisms in this app share. */
    function collapsedController(desc) {
        if (host && host.collapsedToggle) {
            const sel = askHost('collapsedToggle', host.collapsedToggle, [desc.el], null);
            if (sel === null || sel === undefined) return null;
            // Checked before it is used. Unchecked, a toggle that is not there
            // becomes an "open this first" step of its own, which times out
            // naming the host's selector rather than the step's, and the
            // person is told to open something that does not exist.
            if (!isSelector(sel) || !desc.doc.querySelector(sel)) {
                sayOnce('collapsedToggle:' + String(sel), 'TourHost.collapsedToggle named '
                        + String(sel) + ', which matches nothing on the page, so it is not pointed at');
                return null;
            }
            return sel;
        }
        for (let n = desc.el.parentElement; n; n = n.parentElement) {
            if (!n.id) continue;
            const sels = CONFIG.controllersFor(n.id);
            for (let i = 0; i < sels.length; i++) {
                const c = desc.doc.querySelector(sels[i]);
                if (c && c.getAttribute('aria-expanded') === 'false') return sels[i];
            }
        }
        return null;
    }

    /* Waits for the visibility check, watching the attributes that flip it.
       Every modal in this app is in the page at load, so waiting for a NODE
       resolves at once and then points at something hidden. */
    function waitVisible(step, token) {
        return new Promise(function (done) {
            const deadline = Date.now() + targetWaitMs();
            const watchers = [];
            let poll = null, finished = false;

            function stop(result) {
                if (finished) return;
                finished = true;
                watchers.forEach(function (o) { o.disconnect(); });
                clearTimeout(poll);
                done(result);
            }

            function attempt() {
                if (finished) return;
                if (token !== runToken) return stop(null);
                const d = resolve(step);
                if (d) {
                    if (isVisible(d)) return stop({ desc: d });
                    const ctl = collapsedController(d);
                    if (ctl) return stop({ desc: d, controller: ctl });
                }
                if (Date.now() >= deadline) return stop(null);
                clearTimeout(poll);
                poll = setTimeout(attempt, 100);
            }

            const docs = [document];
            const f = step.frame ? frameReady() : null;
            if (f) docs.push(f.doc);
            docs.forEach(function (doc) {
                const o = new MutationObserver(attempt);
                o.observe(doc, { attributes: true, childList: true, subtree: true,
                                 attributeFilter: ['class', 'style', 'hidden'] });
                watchers.push(o);
            });
            attempt();
        });
    }

    function waitFor(test, ms, token) {
        return new Promise(function (done) {
            const until = Date.now() + ms;
            (function tick() {
                if (token !== runToken) return done(null);
                const v = test();
                if (v) return done(v);
                if (Date.now() >= until) return done(null);
                waitTimer = setTimeout(tick, 100);
            })();
        });
    }

    /* ── Steps ─────────────────────────────────────────────────────────────── */
    function onScreen(step, sel) {
        const d = resolve({ frame: step.frame, sel: sel });
        return !!(d && isVisible(d));
    }

    function dropStep(index) {
        steps = steps.slice(0, index).concat(steps.slice(index + 1));
        return show(index);
    }

    async function show(index) {
        const token = ++runToken;
        if (!active) return;
        if (ui) { ui.spot.hidden = true; ui.tip.hidden = true; }
        timedOut = false;
        hideChip();
        if (index >= steps.length) return end('done');
        const step = steps[index];

        /* DROPPED, NOT WAITED FOR, when it does not apply. Removed from the
           list rather than stepped over, so "Step 3 of 9" stays true; the saved
           place is the tour as written, so a reload is not thrown off by it. */
        if (step.when && !onScreen(step, step.when)) return dropStep(index);

        /* ALREADY DONE, dropped the same way: a step whose reveals is on screen
           as it comes up has nothing left to ask. Left in, the tick moved on
           before its card was drawn, so it flickered past and the count skipped
           one. Found in review. */
        if (step.reveals && step.kind !== 'note' && onScreen(step, step.reveals)) {
            return dropStep(index);
        }

        /* THE RIGHT TAB, BY ASKING. Never switched programmatically: being
           guided to click it is the whole product, and a tour that drove the
           page itself would teach nobody anything. */
        /* ASKED NOW, not read off the last poll. A host's tabs are only polled,
           and a guide advances on the click that opened the tab, so the poll
           has usually not seen that tab yet and the step was guided to a tab
           already showing. The prototype's observer updates in time; this
           costs it one extra read. */
        if (step.tab && !step.tabGuide) syncTab();
        if (step.tab && !step.tabGuide && !tabIsActive(step.tab)) {
            const sel = tabButtonFor(step.tab);
            if (sel) {
                steps = steps.slice(0, index).concat([{
                    sel: sel, advance: 'click', tabGuide: step.tab, origin: step.origin,
                    title: 'Open the right tab first',
                    body: 'The next step is on this tab. Click it and the tour carries on.',
                    targetName: 'the tab the next step is on',
                    instruction: 'Open the tab the next step is on',
                }], steps.slice(index));
                return show(index);
            }
            // No such tab on this page. Fall through and let the target wait
            // decide, so a tour spanning two pages is not stuck here.
        }

        // A note has nothing to point at: it warns about a browser dialog,
        // which no overlay can sit on top of.
        if (step.kind === 'note') {
            current = index;
            placedIndex = index;
            saveResume(index);
            build();
            fillTip(step, index);
            positionNote(step);
            ui.tip.focus({ preventScroll: true });
            return;
        }

        if (step.frame && !(await waitFor(frameReady, CONFIG.frameTimeoutMs, token))) {
            if (token !== runToken) return;
            console.warn('[tour] the My Time frame was not ready in time:', describeAllWays(step));
            return showTimeout(index, step);
        }

        const found = await waitVisible(step, token);
        if (token !== runToken) return;

        if (!found) {
            console.warn('[tour] no visible target within the timeout:', describeAllWays(step));
            return showTimeout(index, step);
        }

        if (found.controller) {
            const depth = (step.expandDepth || 0) + 1;
            if (depth > CONFIG.maxExpandDepth) {
                console.warn('[tour] too many nested collapsed panels:', describeAllWays(step));
                return showTimeout(index, step);
            }
            const expand = {
                frame: step.frame, sel: found.controller, advance: 'click',
                title: 'Open this first',
                body: 'This part of the page is folded away. Click here to open it and the tour carries on.',
                targetName: 'the control that opens this part of the page',
                instruction: 'Open the folded part of the page',
                expandFor: step, expandDepth: depth, origin: step.origin,
            };
            steps = steps.slice(0, index).concat([expand], steps.slice(index));
            return show(index);
        }

        current = index;
        placedIndex = -1;
        saveResume(index);
        present(step, found.desc, token);
    }

    /* What a could-not-find card tells the person: the step's task, never its
       selector. "#task-select" meant nothing to anyone reading the card, so a
       person who pressed Continue could not do the step by hand, and the steps
       that depended on it failed too. The selector is for whoever maintains the
       tour, and every path here has already written it to the console. */
    function missingText(step) {
        const thing = step.targetName || 'what this step points at';
        const todo = String(step.instruction || step.title || 'Do this step yourself if you can')
            .trim().replace(/[.!\s]+$/, '');
        return 'We could not find ' + thing + '. ' + todo + ', then press Continue.';
    }

    /* Said on screen, not only in the console. A tour that stops with no
       explanation is indistinguishable from one that is still thinking. */
    function showTimeout(index, step) {
        build();
        current = index;
        placedIndex = index;
        timedOut = true;
        saveResume(index);
        ui.spot.hidden = true;
        ui.cursor.hidden = true;
        hideChip();
        fillTip({ title: 'Could not find the next step',
                  body: missingText(step),
                  timeout: true }, index);
        ui.tip.classList.add('tour-tip--docked');
        ui.tip.hidden = false;
        placeCard(null, step);                  // measured once it is shown
        ui.tip.focus({ preventScroll: true });
    }

    function next(expected) {
        if (!active || expected !== current) return;     // a stale or doubled click
        current = -1;
        show(expected + 1);
    }

    /* ── Drawing ───────────────────────────────────────────────────────────── */
    function build() {
        if (ui) return;
        const spot = document.createElement('div');
        spot.className = 'tour-spot';
        spot.setAttribute(UI, 'spotlight');
        spot.hidden = true;

        const cursor = document.createElement('div');
        cursor.className = 'tour-cursor';
        cursor.setAttribute(UI, 'cursor');
        cursor.setAttribute('aria-hidden', 'true');
        cursor.hidden = true;
        // Built as nodes rather than a markup string, so the engine contains no
        // innerHTML anywhere and 'copy goes in as text' has no exceptions.
        const NS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('viewBox', '0 0 22 22');
        svg.setAttribute('focusable', 'false');
        const path = document.createElementNS(NS, 'path');
        path.setAttribute('d', 'M1 1 L1 17 L5.5 12.8 L8.6 20 L11.4 18.8 L8.4 11.8 L14.6 11.8 Z');
        path.setAttribute('fill', '#fff');
        path.setAttribute('stroke', '#0D1117');
        path.setAttribute('stroke-width', '1.2');
        path.setAttribute('stroke-linejoin', 'round');
        svg.appendChild(path);
        cursor.appendChild(svg);
        // Each animation removes its own class when it ends, so the next step
        // can start it again. Nothing else removes them mid-animation.
        cursor.addEventListener('animationend', function () {
            cursor.classList.remove('tour-cursor--pulse', 'tour-cursor--fade');
        });
        cursorTo = '';

        const tip = document.createElement('div');
        tip.className = 'tour-tip';
        tip.setAttribute(UI, 'tooltip');
        tip.setAttribute('role', 'dialog');
        tip.setAttribute('aria-live', 'polite');
        tip.setAttribute('aria-labelledby', 'tour-tip-title');
        tip.tabIndex = -1;
        tip.hidden = true;

        document.body.appendChild(spot);
        document.body.appendChild(cursor);
        document.body.appendChild(tip);
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'tour-chip';
        chip.setAttribute(UI, 'chip');
        chip.textContent = 'Resume tour';
        chip.hidden = true;
        chip.addEventListener('click', function () {
            const i = current;
            if (i < 0) return;
            current = -1;
            show(i);
        });
        document.body.appendChild(chip);

        ui = { spot: spot, cursor: cursor, tip: tip, chip: chip };
    }

    function fillTip(step, index) {
        const tip = ui.tip;
        tip.textContent = '';                    // copy goes in as text, never as markup

        const title = document.createElement('h2');
        title.className = 'tour-tip__title';
        title.id = 'tour-tip-title';
        title.textContent = step.title || '';

        const body = document.createElement('p');
        body.className = 'tour-tip__body';
        body.textContent = step.body || '';

        const foot = document.createElement('div');
        foot.className = 'tour-tip__foot';

        const progress = document.createElement('span');
        progress.className = 'tour-tip__progress';
        progress.textContent = 'Step ' + (index + 1) + ' of ' + steps.length;

        foot.appendChild(progress);

        /* A COULD-NOT-FIND CARD OFFERS END TOUR, NEVER SKIP. Skip ends the whole
           tour. On a normal step that is what it means. On a card that says the
           step could not be found it reads as "skip this step", and in the Phase A
           breakage a person who pressed it there lost the five steps after the
           one that had moved. Continue moves past the step; End tour is the
           honest name for ending. */
        const missing = !!step.timeout;
        if (missing) {
            const stop = document.createElement('button');
            stop.type = 'button';
            stop.className = 'tour-btn-end';
            stop.textContent = 'End tour';
            stop.addEventListener('click', function () { end('ended-on-missing-step'); });
            foot.appendChild(stop);
        } else {
            const skip = document.createElement('button');
            skip.type = 'button';
            skip.className = 'tour-btn-skip';
            skip.textContent = 'Skip';
            skip.addEventListener('click', function () { end('skip'); });
            foot.appendChild(skip);
        }

        const wantsButton = step.timeout || step.kind === 'note' || step.kind === 'region'
                         || step.advance === 'next';
        if (wantsButton) {
            const go = document.createElement('button');
            go.type = 'button';
            go.className = 'tour-btn-next';
            go.textContent = step.timeout ? 'Continue'
                           : (index === steps.length - 1 ? 'Done' : 'Next');
            go.addEventListener('click', function () { next(index); });
            foot.appendChild(go);
        }

        tip.appendChild(title);
        tip.appendChild(body);
        tip.appendChild(foot);
    }

    /* A note sits beside whatever the last step pointed at, with no spotlight:
       there is nothing to highlight, because the thing it warns about is a
       browser dialog that no overlay can cover. */
    function positionNote(step) {
        ui.spot.hidden = true;
        ui.cursor.hidden = true;
        ui.tip.hidden = false;
        const anchor = step.after
            ? resolve({ frame: step.frame, sel: step.after })
            : null;
        if (anchor && isVisible(anchor)) {
            ui.tip.classList.remove('tour-tip--docked');
            placeCard(rectOf(anchor), step);
        } else {
            ui.tip.classList.add('tour-tip--docked');
            placeCard(null, step);
        }
    }

    /* Which way found this step, said every time a step is shown, so a page
       change the list survived stays visible to whoever maintains the tour. A
       step found by anything but its first way is also a warning, naming how
       many elements each earlier way matched: the handle the step was written
       against has gone, and the next change may take the fallback too. */
    function sayHowFound(step, desc) {
        if (!step.target) { foundBy = step.sel || null; return; }
        foundBy = describeWay(step.target[desc.via]);
        const label = 'step ' + (current + 1) + ' "' + (step.title || '') + '"';
        console.info('[tour] ' + label + ' found by ' + foundBy
                     + ' (way ' + (desc.via + 1) + ' of ' + step.target.length + ')');
        if (desc.via > 0) {
            const missed = step.target.slice(0, desc.via).map(function (t) {
                return describeWay(t) + ' matched ' + matchesOf(desc.doc, t).length;
            });
            console.warn('[tour] ' + label + ' fell back to ' + foundBy + ': ' + missed.join(', '));
        }
    }

    function present(step, desc, token) {
        shownTarget = true;
        sayHowFound(step, desc);
        build();
        fillTip(step, current);
        desc.el.scrollIntoView({ block: 'center', inline: 'nearest',
                                 behavior: reducedMotion() ? 'auto' : 'smooth' });
        settle(step, token).then(function () {
            if (token !== runToken) return;
            place(true);
            ui.tip.focus({ preventScroll: true });
        });
    }

    /* Waits for the scroll to stop moving the target, so the spotlight lands
       where it will stay rather than chasing a smooth scroll. */
    function settle(step, token) {
        return new Promise(function (done) {
            let last = '', still = 0;
            const until = Date.now() + 900;
            (function tick() {
                if (token !== runToken) return done();
                const d = resolve(step), r = d && rectOf(d);
                const key = r ? Math.round(r.left) + ',' + Math.round(r.top) : '';
                still = key === last ? still + 1 : 0;
                last = key;
                if (still >= 3 || Date.now() >= until) return done();
                setTimeout(tick, 50);
            })();
        });
    }

    function place(isNewStep) {
        if (!active || !ui || current < 0) return;
        // Its card is docked and staying, but the page under it can still
        // scroll a keep-clear control into its way, so it is re-searched.
        if (timedOut) return placeCard(null, steps[current]);
        const step = steps[current];
        // Nothing is followed until the step has been presented. Repositioning
        // before that moved the cursor onto the new target while the scroll
        // settled, so it arrived before it ever travelled.
        if (isNewStep) placedIndex = current;
        else if (placedIndex !== current) return;
        if (step.kind === 'note') return positionNote(step);

        const desc = resolve(step);               // re-resolved: nodes get replaced

        if (!desc || !isVisible(desc)) {
            // The target went away: a modal closed, a tab changed. Fall back to
            // a chip rather than a card pinned to nothing.
            ui.spot.hidden = true;
            ui.cursor.hidden = true;
            ui.tip.hidden = true;
            showChip();
            return;
        }
        hideChip();
        ui.tip.classList.remove('tour-tip--docked');
        ui.tip.hidden = false;
        ui.spot.hidden = false;
        // A region is read, not clicked: a cursor on it would say "click here".
        const region = step.kind === 'region';
        ui.cursor.hidden = region;

        const r = rectOf(desc);
        const s = ui.spot.style;
        s.left   = (r.left - CONFIG.pad) + 'px';
        s.top    = (r.top  - CONFIG.pad) + 'px';
        s.width  = (r.width  + CONFIG.pad * 2) + 'px';
        s.height = (r.height + CONFIG.pad * 2) + 'px';

        if (!region) moveCursor(centerOf(r), isNewStep);
        placeCard(r, step);
    }

    function showChip() {
        if (!ui) return;
        ui.chip.hidden = false;
    }

    function hideChip() {
        if (ui) ui.chip.hidden = true;
    }

    function moveCursor(c, isNewStep) {
        const el = ui.cursor;
        const to = 'translate(' + Math.round(c.x) + 'px,' + Math.round(c.y) + 'px)';

        if (!isNewStep) {
            // Following a target that moved, not arriving at a new one. This
            // runs on every 250ms tick, so when nothing moved it must do nothing
            // at all. An earlier version reset the transition and stripped the
            // animation classes here, which snapped the cursor to its
            // destination and cut the pulse off within a quarter second.
            // Compared against what was written, because style.transform reads
            // back normalised and would never match.
            if (cursorTo === to) return;
            cursorTo = to;
            if (Date.now() < travelUntil) {
                el.style.transform = to;          // mid-travel: retarget, keep moving
            } else {
                el.style.transition = 'none';
                el.style.transform = to;
                void el.offsetWidth;              // commit the snap before re-enabling
                el.style.transition = '';
            }
            return;
        }

        const token = runToken;
        const travel = !reducedMotion() && !!lastCenter;
        el.classList.remove('tour-cursor--pulse', 'tour-cursor--fade');
        void el.offsetWidth;                      // lets the same class restart its animation
        cursorTo = to;
        if (travel) {
            el.style.transition = '';
            el.style.transform = to;
            travelUntil = Date.now() + 650;
            setTimeout(function () {
                if (ui && ui.cursor === el && token === runToken) {
                    el.classList.add('tour-cursor--pulse');
                }
            }, 620);
        } else {
            el.style.transition = 'none';
            el.style.transform = to;
            void el.offsetWidth;
            el.style.transition = '';
            el.classList.add(reducedMotion() ? 'tour-cursor--fade' : 'tour-cursor--pulse');
        }
        lastCenter = c;
    }

    /* ── Where the card goes ──────────────────────────────────────────────────
     * A CARD NEVER COVERS WHAT SOMEBODY HAS TO CLICK. Found on the Ortho host:
     * cards placed below or above their own target sat over the tab bar, a
     * person clicked a tab, the click landed on the card, nothing happened,
     * and only Skip answered. The rule it broke, for every card:
     *
     *   - its own target stays clickable, spotlight padding included
     *   - so does everything in TourHost.keepClear, which a host sets for the
     *     controls no card on the page may ever cover (Ortho: its tabs)
     *   - and everything in the step's own keepClear, for any other control
     *     that card talks about
     *
     * So the position is SEARCHED. Candidates are tried in order and the first
     * that covers none of those wins. The order starts where cards always went,
     * below and then above, so a layout that was never a problem looks the
     * same. Then right-aligned, then beside, then the window's corners. A
     * docked card, one with nothing to point at, starts from the corner above
     * the trigger where it always sat and goes through the same search.
     *
     * Only what is on screen counts. A control that is hidden cannot be clicked
     * whatever covers it. */
    function paddedRect(r) {
        return { left: r.left - CONFIG.pad, top: r.top - CONFIG.pad,
                 right: r.right + CONFIG.pad, bottom: r.bottom + CONFIG.pad };
    }

    function overlapArea(a, b) {
        const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        return w > 0 && h > 0 ? w * h : 0;
    }

    function keepClearRects(step) {
        const out = [];
        [host && host.keepClear, step && step.keepClear].forEach(function (sel) {
            if (!sel) return;
            let nodes = [];
            try { nodes = document.querySelectorAll(sel); }
            catch (e) { return; }                 // a custom step is not checked; a bad one names nothing
            for (let i = 0; i < nodes.length; i++) {
                const d = { el: nodes[i], doc: document, frameEl: null };
                if (isVisible(d)) out.push(paddedRect(rectOf(d)));
            }
        });
        return out;
    }

    function cardCandidates(r, w, h, vw, vh) {
        const g = CONFIG.gap, p = CONFIG.pad;
        const corners = [
            { left: vw - w - 20, top: vh - h - 72 },   // above the trigger: where it always docked
            { left: 20,          top: vh - h - 72 },
            { left: vw - w - 20, top: 20 },
            { left: 20,          top: 20 },
        ];
        if (!r) return corners;
        const below = r.bottom + p + g, above = r.top - p - g - h;
        return [
            { left: r.left,             top: below },
            { left: r.left,             top: above },
            { left: r.right - w,        top: below },
            { left: r.right - w,        top: above },
            { left: r.right + p + g,    top: r.top },
            { left: r.left - p - g - w, top: r.top },
        ].concat(corners);
    }

    /* WHEN NO CANDIDATE IS CLEAR, THE LEAST BAD, AND THE RANKING IS THE RULE.
       Covering the card's OWN TARGET is worse than covering anything else, by
       any amount. The card exists to get that one control clicked, and a card
       on top of it asks for a click nobody can make: the exact fault this
       search was written for. A keep-clear control covered is the lesser
       fault, because the step can still be done.
       So candidates are compared on own-target overlap FIRST and on everything
       else only to break a tie there. Two separate numbers, deliberately never
       one weighted sum: enough keep-clear overlap would outweigh any weight,
       and "the card hid its own button because that covered fewer pixels" is
       the result a sum eventually produces. Ties after that go to the earlier
       candidate, which keeps the familiar positions. */
    function lessBad(a, b) {
        if (a.own !== b.own) return a.own < b.own;
        return a.rest < b.rest;
    }

    /* r: the target's rect, or null for a docked card. */
    function placeCard(r, step) {
        const tip = ui.tip;
        const vw = global.innerWidth, vh = global.innerHeight;
        const w = tip.offsetWidth, h = tip.offsetHeight;
        const own = r ? paddedRect(r) : null;
        const clear = keepClearRects(step);
        const list = cardCandidates(r, w, h, vw, vh);
        let best = null;
        for (let i = 0; i < list.length; i++) {
            // Rounded before it is scored, so what is scored is what is drawn.
            const left = Math.round(Math.min(Math.max(8, list[i].left), Math.max(8, vw - w - 8)));
            const top  = Math.round(Math.min(Math.max(8, list[i].top),  Math.max(8, vh - h - 8)));
            const box = { left: left, top: top, right: left + w, bottom: top + h };
            const score = {
                box: box,
                own: own ? overlapArea(box, own) : 0,
                rest: clear.reduce(function (n, k) { return n + overlapArea(box, k); }, 0),
            };
            if (!best || lessBad(score, best)) best = score;
            if (best.own === 0 && best.rest === 0) break;
        }
        tip.style.left = best.box.left + 'px';
        tip.style.top  = best.box.top + 'px';
    }

    function schedule() {
        if (frameReq) return;
        frameReq = requestAnimationFrame(function () {
            frameReq = 0;
            place(false);
        });
    }

    /* Layout shifts that fire no event - the frame resizing itself from a
       postMessage, the running state appearing - are caught here, as is an
       expand step whose panel the person opened some other way. */
    function tick() {
        if (!active || current < 0) return;
        const step = steps[current];
        if (step.tabGuide && tabIsActive(step.tabGuide)) return next(current);
        if (step.expandFor) {
            const d = resolve(step.expandFor);
            if (d && isVisible(d)) return next(current);
        }
        // Before schedule(): the thing that appeared usually hid the target,
        // and placing first would flash the chip. Watched on a timed-out card
        // too, deliberately: a panel that shows up late still carries the tour
        // on rather than leaving the person on "could not find".
        if (step.reveals) {
            const r = resolve({ frame: step.frame, sel: step.reveals });
            if (r && isVisible(r)) return next(current);
        }
        schedule();
    }

    /* ── Events ────────────────────────────────────────────────────────────── */
    function onClick(e) {
        if (!active || current < 0) return;
        const step = steps[current];
        // A region is read, never clicked on: a click inside it is the person
        // looking, and moves nothing on. Host steps are refused a clicked
        // region; the prototype's own steps are not checked, so it holds here.
        if (step.advance !== 'click' || step.kind === 'region') return;
        const desc = resolve(step);                // never a node held from earlier
        if (!desc || !e.target || e.target.ownerDocument !== desc.doc) return;
        // Inside the element this step resolved to, however it was found.
        if (e.target !== desc.el && !desc.el.contains(e.target)) return;
        const expected = current;
        // After the app's own handlers, so the next step sees what the click did.
        setTimeout(function () { next(expected); }, 0);
    }

    function onKey(e) {
        if (active && e.key === 'Escape') end('escape');
    }

    function listenTo(doc) {
        if (listening.indexOf(doc) !== -1) return;
        doc.addEventListener('click', recClick, true);
        doc.addEventListener('click', onClick, true);
        doc.addEventListener('keydown', onKey, true);
        doc.addEventListener('scroll', schedule, true);
        if (doc.defaultView) doc.defaultView.addEventListener('resize', schedule);
        listening.push(doc);
    }

    function stopListening() {
        if (recording) return;        // record mode is still using these documents
        listening.forEach(function (doc) {
            try {
                doc.removeEventListener('click', recClick, true);
                doc.removeEventListener('click', onClick, true);
                doc.removeEventListener('keydown', onKey, true);
                doc.removeEventListener('scroll', schedule, true);
                if (doc.defaultView) doc.defaultView.removeEventListener('resize', schedule);
            } catch (err) { /* a frame document that has since gone away */ }
        });
        listening.length = 0;
    }

    /* ── Record mode ──────────────────────────────────────────────────────────
     * A person turns it on, does the task once, and presses Stop. Out comes a
     * step list this same engine can play, checked by the same rules a host's
     * steps are checked by. It is not a separate tool: the clicks arrive on the
     * capture listeners the tour already installs, the ways are built with the
     * strategies the tour already resolves with, in the same order, and the
     * result goes through stepProblems() before anyone sees it.
     *
     * WHAT IT REFUSES TO KEEP
     *   its own bar, and the tour trigger
     *   anything typed: a field is recorded as a field, never with its contents
     *   any page text but the visible label of the control that was clicked,
     *   and nothing at all from content, where the words are somebody's work
     *
     * WHAT IT REFUSES TO GUESS
     *   the words on the card. It cannot know what a control is for, so it
     *   writes a placeholder and marks the step for review. A placeholder the
     *   author has to replace is honest; an invented instruction is not.
     *
     * CONTENT DEGRADES WIDE, NEVER WRONG. Part 3 measured a step pointing at a
     * table row through a day group's classes: the markup moved and the way
     * that still matched exactly one element matched YESTERDAY's row, under a
     * card saying "the time you just saved". Being unique is not being right.
     * So a click on something the page does not name becomes a REGION on the
     * nearest area the app itself names, read rather than clicked.
     *
     * THE WORDS ON A CONTROL ARE SCREENED, AND WHAT THE SCREEN CANNOT JUDGE IS
     * SAID. A control's own words become its step's title, its targetName, a
     * text or label way, and its review note, and a customer's name on a link is
     * words like any other. Withheld from all four places: words holding two
     * digits in a row (a date, an amount, a record number) and words holding
     * an email address. A withheld control is called by what it is, "a link in
     * the "orders" area", and a step left with no way to find it becomes a
     * region. A control in one row of a list keeps NOTHING of its own, not its
     * words and not its ids, which name the record as often as the words do:
     * it is content, and becomes a region on the list, found from outside the
     * row (recWays, recContainer). Everything else is kept and marked
     * unchecked, on every step and above the copy box, because "Jane Smith"
     * and "Log time" look the same to the recorder and no rule tells them
     * apart. A screen that misses must not read like one that passed. No part
     * of a page's address is kept at all: pages are numbered (recPage).
     *
     * IT OUTLIVES A PAGE LOAD. The recording is kept in sessionStorage under its
     * own key after every change, and a page that loads the engine takes it up:
     * a link, a reload, Back, or a page restored from the back-forward cache. A
     * page that does not load the engine records nothing and shows no bar, so
     * the next page that does says so, plainly, on the bar and in the review.
     * Found by recording a list whose rows link by name: a navigating link lost
     * the whole recording, and that loss was half of what kept names out of
     * it. The two halves landed together because either alone makes it worse.
     */
    const REC = {
        /* What a click lands on that a step can point at. Anything else is
           content: the words in it belong to whoever did the work.

           NOT '[data-tab]', which was here and was wrong: in this app the tab
           PANELS carry data-tab as well as the tab buttons, so a click on a
           row walked up and found the panel "interactive" and recorded the
           whole panel as a click step. A measured lesson about how easily
           "looks like a control" catches a container. */
        interactive: 'button, a[href], input, select, textarea, summary, label,'
                   + ' [role="button"], [role="tab"], [role="link"],'
                   + ' [data-section-toggle], [onclick]',
        fields: ['INPUT', 'TEXTAREA', 'SELECT'],
        // A NAME, not data. dg-week-2026-09-17 and entry-row-4182 are this
        // day and this record: they name one afternoon's page, not the app.
        name: /^[A-Za-z][A-Za-z0-9_-]*$/,
        dataish: /\d\d/,
        // An address has a shape, and a shape is all the screen can go on.
        email: /[^\s@]+@[^\s@]+\.[^\s@]+/,
        /* ONE ROW OF SEVERAL: its controls are one record's, and so are their
           words. Not the app's own lists, a menu or a tab bar, whose words are
           the app's; those are left to the unchecked mark like any label. */
        rows: 'tr, li, [role="row"], [role="listitem"]',
        appLists: 'nav, [role="navigation"], [role="menu"], [role="menubar"],'
                + ' [role="tablist"], [role="tree"]',
        why: {
            number: 'they hold a number, which is usually a date, an amount or a record',
            email: 'they hold an email address',
        },
        unchecked: 'these words were taken off the page and could not be checked: the recorder '
                 + 'cannot tell a person\'s or a customer\'s name from a button\'s label. If they '
                 + 'are somebody\'s data, replace them in the title and the name, and take out '
                 + 'the text or label way that holds them',
        maxLabel: 60,
        // Classes that describe the moment rather than the thing.
        stateClass: /^(is-|has-|js-|tour-)|^(active|selected|current|open|closed|hidden|shown|show|on|off|disabled|loading|error|success|highlight)$/,
        instruction: 'REPLACE ME: say what the person should do here',
        body: 'REPLACE ME: say what this step is showing.',
        placeholderTitle: 'This part of the page',
        watchMs: 400,
        pollMs: 500,
    };

    let recording  = false;
    let recSteps   = [];       // contract steps, in the order they were made
    let recReview  = [];       // one entry per step: why a person still has to look
    let recUi      = null;     // { bar, count, note, stop, out }
    let recPoll    = null;
    let recLast    = null;     // the element the last step points at, so a
                               // double click on one control is one step
    let recDump    = null;     // what the last Stop handed over. A person
                               // presses the button and reads the panel, so
                               // the list has to be fetchable afterwards too
    let recLink    = null;     // the last click, if it was on a link that may
                               // take this page elsewhere: read at pagehide
    let recPages   = [];       // a key per page the recording has been on, in
                               // the order it got there: page 1, page 2

    function recIsName(value) {
        return typeof value === 'string' && REC.name.test(value) && !REC.dataish.test(value);
    }

    function recLabelText(el) {
        const labels = el.labels ? Array.prototype.slice.call(el.labels) : [];
        for (let i = 0; i < labels.length; i++) {
            const t = recWords(labels[i].textContent);
            if (t && t.length <= REC.maxLabel) return t;
        }
        return null;
    }

    // A field's contents are not its name: a select reads out its options and
    // a filled-in box reads out somebody's answer.
    function recIsField(el) {
        return REC.fields.indexOf(el.tagName) !== -1 || !!el.isContentEditable;
    }

    // Words as they are written, for a person to read on a card. readable()
    // is for MATCHING and strips the punctuation off the ends, which turns
    // "Notes (optional)" into "Notes (optional".
    function recWords(text) {
        return String(text || '').replace(/\s+/g, ' ').trim();
    }

    // Why these words may not be kept, or null when nothing about them says so.
    function recWithheld(words) {
        if (REC.dataish.test(words)) return REC.why.number;
        if (REC.email.test(words)) return REC.why.email;
        return null;
    }

    /* The row of several alike that el is in, starting at el itself: a table
       row among rows, a list item among items. The OUTERMOST, so a row inside
       a record's row is still that record's. The app's own lists are not rows. */
    function recRowOf(el) {
        const body = el.ownerDocument.body;
        let row = null;
        for (let n = el; n && n !== body; n = n.parentElement) {
            if (!n.matches(REC.rows) || !n.parentElement || n.closest(REC.appLists)) continue;
            const alike = Array.prototype.some.call(n.parentElement.children, function (c) {
                return c !== n && c.tagName === n.tagName && c.matches(REC.rows);
            });
            if (alike) row = n;
        }
        return row;
    }

    function recInRow(el) {
        return !!recRowOf(el);
    }

    /* What a control is, in the recorder's own words, for a step whose words
       were withheld. The area is the one the app names, already screened. */
    function recKindOf(el) {
        const role = el.getAttribute('role');
        const kind = recIsField(el) ? 'a field'
                   : el.tagName === 'A' || role === 'link' ? 'a link'
                   : role === 'tab' ? 'a tab'
                   : el.tagName === 'BUTTON' || el.tagName === 'SUMMARY' || role === 'button' ? 'a button'
                   : 'a control';
        const area = el.parentElement ? recContainer(el.parentElement) : null;
        return area ? kind + ' in the "' + area + '" area' : kind;
    }

    /* What a control may be called in a recording. The words on the control
       itself, and nowhere else on the page, each source SCREENED before it is
       used: its own text, then its aria-label or title, then its <label>.
         name       what the title, the targetName and the review are given
         text, label  whether those words may also become a way
         withheld   why any words were left out
         unchecked  the name is words off the page the screen could not judge */
    /* A control in a list row never reaches here to be named: it has no ways
       and becomes a region (recWays), so the row rule is not repeated. It was,
       and the overnight run found it could not be reached: the mutation that
       removed it passed every check. */
    function recNaming(el) {
        const withheld = [];
        function screen(words) {
            if (!words) return '';
            const why = recWithheld(words);
            if (!why) return words;
            if (withheld.indexOf(why) === -1) withheld.push(why);
            return '';
        }
        const own = recIsField(el) ? '' : recWords(el.textContent);
        const text = screen(own.length <= REC.maxLabel ? own : '');
        const aria = el.getAttribute ? (el.getAttribute('aria-label') || el.getAttribute('title')) : null;
        // Screened whole, then cut: a number past the cut is still a number.
        const said = screen(recWords(aria)).slice(0, REC.maxLabel);
        const label = screen(recLabelText(el));
        const words = text || said || label;
        const out = { text: !!text, label: !!label, withheld: withheld, unchecked: !!words };
        if (words) out.name = words;
        else if (withheld.length) out.name = recKindOf(el);
        else if (el.id && recIsName(el.id)) { out.name = el.id; out.unchecked = true; }
        else out.name = el.tagName.toLowerCase();
        return out;
    }

    function recWithheldNote(naming) {
        return 'the words on this control were withheld because ' + naming.withheld.join(', and ')
             + (naming.unchecked ? '. It is named by other words it carries, which were kept'
                                 : '. It is called by what it is until you name it');
    }

    // Every data- attribute whose value reads as a name, in the order written.
    function recDataAttrs(el) {
        const out = [];
        const attrs = el.attributes || [];
        for (let i = 0; i < attrs.length; i++) {
            const a = attrs[i];
            if (a.name.indexOf('data-') !== 0 || a.name.indexOf('data-tour') === 0) continue;
            if (!recIsName(a.value)) continue;   // a date or a record number is not a name
            out.push({ by: 'data', attr: a.name, value: a.value });
        }
        return out;
    }

    /* A class and attribute path, scoped to the nearest named area. NEVER a
       position: :nth-child(2) is the guess Part 3 caught being unique and
       wrong. The data attributes go in here too, because a name the element
       SHARES - this app gives .tab[data-tab="log"] and its panel the same
       data-tab - is still what the element is called; it just needs the tag
       and the class to say which of the two is meant. */
    function recCssWay(el) {
        const classes = Array.prototype.filter.call(el.classList || [], function (c) {
            return !REC.stateClass.test(c);
        });
        const attrs = recDataAttrs(el).map(function (t) {
            return '[' + t.attr + '=' + quoted(t.value) + ']';
        });
        if (!classes.length && !attrs.length) return null;
        let scope = '';
        for (let n = el.parentElement; n; n = n.parentElement) {
            if (n.id && recIsName(n.id)) { scope = '#' + n.id + ' '; break; }
        }
        const own = classes.length ? '.' + classes.join('.') : '';
        return { by: 'css', value: scope + el.tagName.toLowerCase() + own + attrs.join('') };
    }

    /* The ways this element can be found, in the engine's own order, keeping
       only those that match IT and nothing else in its document. The
       exactly-one rule is applied here, at recording time, so the list handed
       over cannot contain a way that would be skipped at playback. */
    function recWays(el, doc) {
        const out = [];
        function add(t) {
            if (!t) return;
            const hits = matchesOf(doc, t);
            if (hits.length === 1 && hits[0] === el) out.push(t);
        }
        /* A CONTROL IN ONE ROW OF A LIST HAS NO WAYS OF ITS OWN. Everything
           that could pick it out is the row's: its words, and its id and data
           attributes too, which name the record as often as the words do
           (id="cust-delia-marchetti"). Withholding only the words handed the
           name over in the target list under a title that looked screened,
           which the review found. And a way that picks out one row is Part 3's
           step that is unique and wrong. So it becomes a region, as content. */
        if (recInRow(el)) return out;
        // Words the screen withheld never become a way: a way is copied out
        // with the rest of the step, and is the one place an author is least
        // likely to look.
        const naming = recNaming(el);
        if (el.id && recIsName(el.id)) add({ by: 'id', value: el.id });
        recDataAttrs(el).forEach(add);
        const lab = recLabelText(el);
        if (lab && naming.label) add({ by: 'label', value: lab });
        const own = recIsField(el) ? '' : recWords(el.textContent);
        if (own && own.length <= REC.maxLabel && naming.text) add({ by: 'text', value: own });
        add(recCssWay(el));
        return out;
    }

    /* Does the page NAME this element? An id, a data attribute, or its own
       visible words - whether or not that name is unique. A tab button and
       its panel share data-tab in this app: the button is still named, it
       just takes the tag and the class as well to say which one is meant.
       Classes alone are not a name, which is what keeps content out: a row
       has nothing but the markup around it. */
    function recIsNamed(el) {
        if (el.id && recIsName(el.id)) return true;
        if (recDataAttrs(el).length) return true;
        if (recLabelText(el)) return true;
        const own = recIsField(el) ? '' : recWords(el.textContent);
        return !!(own && own.length <= REC.maxLabel);
    }

    /* The nearest area the app itself names, walking out from the click, and
       from OUTSIDE any row the click is in. A row's own ids name its record as
       its words do: walking out from a customer's link found the link's own
       id="cust-delia-marchetti" and pointed a region at her by name. */
    function recContainer(el) {
        const row = recRowOf(el);
        for (let n = row ? row.parentElement : el; n; n = n.parentElement) {
            if (n.id && recIsName(n.id)) return n.id;
        }
        return null;
    }

    /* One review entry per step, saying which page it was on and whether its
       words came off that page: 'withheld' when the screen took them out,
       'unchecked' when they were kept without anything able to vouch for them. */
    function recPush(el, step, notes, words) {
        recSteps.push(step);
        const why = notes.concat(['the name and the instruction are placeholders: say what this step is for']);
        const entry = { step: recSteps.length, title: step.title, page: recPage(), why: why };
        if (words) entry.words = words;
        recReview.push(entry);
        recLast = el;
        recNotice('');
        recChanged();
    }

    function recElementStep(el, ways, doc, inFrame) {
        if (recLast === el) return null;              // the same control twice is one step
        const field = REC.fields.indexOf(el.tagName) !== -1 || el.isContentEditable;
        const naming = recNaming(el);
        const label = naming.name;
        const step = { title: label, body: REC.body,
                       targetName: label, instruction: REC.instruction,
                       target: ways, advance: field ? 'next' : 'click' };
        if (inFrame) step.frame = true;
        if (activeTabName) step.tab = activeTabName;
        // The recorder's own words for a withheld control start a sentence as a
        // title and sit inside one as a targetName: "We could not find a link".
        if (!naming.unchecked && naming.withheld.length) {
            step.title = label.charAt(0).toUpperCase() + label.slice(1);
        }
        const notes = [];
        if (field) {
            notes.push('a field: the tour asks the person to fill it in and waits for Next. '
                       + 'What was typed into it was not recorded');
        }
        if (naming.withheld.length) notes.push(recWithheldNote(naming));
        if (naming.unchecked) notes.push(REC.unchecked);
        recPush(el, step, notes, naming.unchecked ? 'unchecked' : naming.withheld.length ? 'withheld' : null);
        return step;
    }

    /* Wide, not wrong: the nearest named area, read rather than clicked, and
       carrying none of the words that were in it. */
    /* `what` says, without its words, what was clicked, for the note when the
       click lands in the area the last step already points at. */
    function recRegionStep(el, doc, inFrame, why, words, what) {
        const id = recContainer(el);
        if (!id) {
            recReview.push({ step: null, title: null, page: recPage(), why: [
                'a click was not recorded: nothing around it has a name the tour can use, '
                + 'so there was nothing to point at' ] });
            recChanged();
            return null;
        }
        const container = doc.getElementById(id);
        /* THE SAME AREA TWICE IS ONE STEP, AND THE AUTHOR IS TOLD. This used to
           return without a word, and three clicks on three different links
           vanished from a recording: nothing said they had happened. */
        if (recLast === container) {
            recFold('another click in this area was not made a step of its own, because this '
                    + 'step already points at it: it was on '
                    + (what || 'something with no name of its own'));
            return null;
        }
        const step = { title: REC.placeholderTitle, body: REC.body,
                       targetName: 'this part of the page', instruction: REC.instruction,
                       kind: 'region', target: [{ by: 'id', value: id }], advance: 'next' };
        if (inFrame) step.frame = true;
        if (activeTabName) step.tab = activeTabName;
        recPush(container, step, [why
                || ('what was clicked has no name of its own, so this points at the "' + id
                    + '" area around it and is read, not clicked. Check it is the right area')],
                words);
        return step;
    }

    // Said on the step the click was folded into, which is the last one made.
    function recFold(line) {
        for (let i = recReview.length - 1; i >= 0; i--) {
            if (recReview[i].step === recSteps.length) { recReview[i].why.push(line); break; }
        }
        recChanged();
    }

    /* What the click OPENED, so playback can skip the step when the thing is
       already open: the same two signals the engine reads when it inserts an
       "open this first" step. Only when the thing has a name that will still
       be there tomorrow - a day group names its body with today's date, and a
       recording that pointed at that would be wrong by the morning. */
    function recWatchWhatItOpened(step, el, doc) {
        /* READ OFF THE THING ITSELF, not off the control. The control is often
           replaced by the app's own re-render on the click - this app rewrites
           whole panels - and the fresh node still says aria-expanded="false"
           on the element the recorder is holding, which is detached. What the
           tour cares about is the same thing it checks at playback: is the
           revealed part on the page now, when it was not before. */
        const controls = recControlledIds(el, doc).filter(function (id) {
            return !recOnScreen(doc, '#' + id);
        });
        const before = recDialogIds(doc);
        setTimeout(function () {
            if (!recording || recSteps.indexOf(step) === -1) return;
            let opened = null;
            for (let i = 0; i < controls.length && !opened; i++) {
                if (recOnScreen(doc, '#' + controls[i])) opened = controls[i];
            }
            if (!opened) {
                const now = recDialogIds(doc);
                for (let i = 0; i < now.length; i++) {
                    if (before.indexOf(now[i]) === -1) { opened = now[i]; break; }
                }
            }
            if (!opened) return;
            if (!recIsName(opened)) {
                recReview.push({ step: recSteps.indexOf(step) + 1, title: step.title, page: recPage(), why: [
                    'this click opened something the page only names with today\'s date, '
                    + 'so the recording does not rely on it. Say so in the words instead' ] });
                recChanged();
                return;
            }
            if (step.kind !== 'region' && step.advance === 'click') step.reveals = '#' + opened;
            recChanged();
        }, REC.watchMs);
    }

    /* What this control points at, if anything: aria-controls, or a data
       attribute whose VALUE is the name of an element on the page. The second
       is not a guess about this app - it is how a control says "I am about
       that thing" when it has no aria-controls, and the engine's own
       controllersFor() reads exactly the same two shapes. */
    function recControlledIds(el, doc) {
        if (!el || !el.getAttribute) return [];
        const out = [];
        const aria = el.getAttribute('aria-controls');
        if (aria) out.push(aria);
        const attrs = el.attributes || [];
        for (let i = 0; i < attrs.length; i++) {
            const a = attrs[i];
            if (a.name.indexOf('data-') !== 0 || a.name.indexOf('data-tour') === 0) continue;
            if (a.value && out.indexOf(a.value) === -1 && doc.getElementById(a.value)) out.push(a.value);
        }
        return out;
    }

    // Visible in this document, by the engine's own reckoning.
    function recOnScreen(doc, sel) {
        let el = null;
        try { el = doc.querySelector(sel); } catch (e) { return false; }
        return !!el && isVisible({ el: el, doc: doc, frameEl: doc === document ? null : frameElOf(doc) });
    }

    function frameElOf(doc) {
        const f = frameReady();
        return f && f.doc === doc ? f.frameEl : null;
    }

    // Dialogs and overlays that are on screen right now, by name.
    function recDialogIds(doc) {
        const out = [];
        const nodes = doc.querySelectorAll('[role="dialog"], [aria-modal="true"], .modal, .overlay');
        Array.prototype.forEach.call(nodes, function (n) {
            if (!n.id || n.closest('[' + UI + ']')) return;
            const r = n.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && styleOf(n).visibility !== 'hidden') out.push(n.id);
        });
        return out;
    }

    function recClick(e) {
        if (!recording || !e.target || e.target.nodeType !== 1) return;
        // Never the recorder's own bar, never the tour's trigger.
        if (e.target.closest('[' + UI + '], [data-tour-trigger]')) return;
        const doc = e.target.ownerDocument;
        const inFrame = doc !== document;
        syncTab();                        // the tab as it is at the click, not at the last poll
        recLink = recLinkOf(e, doc);
        const control = e.target.closest(REC.interactive);
        let step = null;
        if (control && recIsNamed(control)) {
            const ways = recWays(control, doc);
            const withheld = recNaming(control).withheld;
            const row = recInRow(control);
            // Named, but nothing found it on its own: point wide rather than
            // hand over a way that would be skipped at playback. The same when
            // the screen took away the only words that could find it, and for
            // a control in one row of a list, which keeps nothing of its own.
            step = ways.length ? recElementStep(control, ways, doc, inFrame)
                 : row
                    ? recRegionStep(control, doc, inFrame,
                                    'this control sits in one row of a list, so its words, its id and '
                                    + 'its data attributes all belong to that row: none of them was '
                                    + 'kept, and the step points at the area around it',
                                    'withheld', 'a control in one row of a list, none of whose names was kept')
                 : withheld.length
                    ? recRegionStep(control, doc, inFrame,
                                    'the words on this control were withheld because '
                                    + withheld.join(', and ') + ', and nothing else could pick it '
                                    + 'out, so the step points at the area around it',
                                    'withheld', 'a control whose words were withheld')
                    : recRegionStep(control, doc, inFrame,
                                    'this control has a name but nothing could pick it out '
                                    + 'from the others, so the step points at the area around it',
                                    null, 'a control with a name that nothing could pick out');
        } else {
            // Content, or a control the page does not name: a row, a cell,
            // somebody's words. Never an element step.
            step = recRegionStep(control || e.target, doc, inFrame);
        }
        if (step) recWatchWhatItOpened(step, control || e.target, doc);
    }

    function recBar() {
        if (recUi) return recUi;
        const bar = document.createElement('div');
        bar.className = 'tour-rec';
        bar.setAttribute(UI, 'recorder');
        const dot = document.createElement('span');
        dot.className = 'tour-rec__dot';
        dot.setAttribute('aria-hidden', 'true');
        const count = document.createElement('span');
        count.className = 'tour-rec__count';
        count.setAttribute('data-tour-rec', 'count');
        count.setAttribute('aria-live', 'polite');
        const stop = document.createElement('button');
        stop.type = 'button';
        stop.className = 'tour-rec__stop';
        stop.setAttribute('data-tour-rec', 'stop');
        stop.textContent = 'Stop';
        stop.addEventListener('click', function () { recStop(); });
        // What a page load did to the recording, said to the person on the bar.
        const note = document.createElement('span');
        note.className = 'tour-rec__note';
        note.setAttribute('data-tour-rec', 'notice');
        note.setAttribute('aria-live', 'polite');
        note.hidden = true;
        bar.appendChild(dot);
        bar.appendChild(count);
        bar.appendChild(note);
        bar.appendChild(stop);
        const out = document.createElement('div');
        out.className = 'tour-rec__out';
        out.setAttribute(UI, 'recording');
        out.hidden = true;
        document.body.appendChild(bar);
        document.body.appendChild(out);
        recUi = { bar: bar, count: count, note: note, stop: stop, out: out };
        return recUi;
    }

    function recDraw() {
        if (!recUi) return;
        const n = recSteps.length;
        recUi.count.textContent = n + (n === 1 ? ' step recorded' : ' steps recorded');
    }

    function recNotice(text) {
        if (!recUi) return;
        recUi.note.textContent = text;
        recUi.note.hidden = !text;
    }

    // After every change: kept for the next page, and counted on the bar.
    function recChanged() {
        recSave(null);
        recDraw();
    }

    /* ── Record mode across page loads ────────────────────────────────────────
     * sessionStorage, under the recorder's own key and no other: it lasts as
     * long as the tab, which is as long as a recording can, and it is gone when
     * the tab is. Never localStorage, which would keep what was recorded on
     * the machine after the person had closed the tab and walked away. */
    function recSave(heading) {
        if (!recording) return;
        try {
            sessionStorage.setItem(CONFIG.recordKey, JSON.stringify({
                steps: recSteps, review: recReview, pages: recPages,
                at: recPageKey(location.href), heading: heading || null }));
        } catch (e) {
            warnOnce('record-storage', 'this browser would not keep the recording, so it will not '
                     + 'survive leaving this page: press Stop before you go');
        }
    }

    function recSaved() {
        let saved = null;
        try { saved = JSON.parse(sessionStorage.getItem(CONFIG.recordKey) || 'null'); }
        catch (e) { return null; }
        return saved && Array.isArray(saved.steps) && Array.isArray(saved.review) ? saved : null;
    }

    function recForget() {
        try { sessionStorage.removeItem(CONFIG.recordKey); } catch (e) { /* nothing was kept */ }
    }

    /* NO PART OF AN ADDRESS GOES INTO A RECORDING. A path carries record ids
       and sometimes names, a NetSuite record's among them, and a recording
       gets emailed. Every part of a path is one the recorder cannot vouch for,
       so replacing the unknown parts with * replaces them all, and pages are
       NUMBERED instead, in the order the recording reached them: "page 2".
       That is enough to match them at playback, and step order says which is
       which. To tell one page from another it keeps a hash of each path, in
       this tab's sessionStorage and nowhere else, and never shows it. The first
       version kept the path with only its digits replaced, which a name in an
       address (/customers/delia-marchetti) walked straight through. */
    function recPageKey(href) {
        let u;
        try { u = new URL(href, location.href); } catch (e) { return 'elsewhere'; }
        if (u.origin !== location.origin) return 'elsewhere';
        let h = 5381;
        for (let i = 0; i < u.pathname.length; i++) h = ((h << 5) + h + u.pathname.charCodeAt(i)) | 0;
        return 'p' + (h >>> 0).toString(36);
    }

    // This page, as a recording names it, numbered the first time it is reached.
    function recPage() {
        const key = recPageKey(location.href);
        if (recPages.indexOf(key) === -1) recPages.push(key);
        return 'page ' + (recPages.indexOf(key) + 1);
    }

    function recPageName(key) {
        const i = recPages.indexOf(key);
        return i === -1 ? 'a page it did not see' : 'page ' + (i + 1);
    }

    /* A click on a link that may take THIS page somewhere else. Whether it
       did is read at pagehide, once the app has had its say: a link the app
       handles itself calls preventDefault and goes nowhere. */
    function recLinkOf(e, doc) {
        if (doc !== document) return null;          // a frame's link moves the frame
        const a = e.target.closest('a[href]');
        if (!a || a.hasAttribute('download')) return null;
        const target = (a.getAttribute('target') || '').toLowerCase();
        if (target && ['_self', '_top', '_parent'].indexOf(target) === -1) return null;
        // An SVG link's href is an object, not the address.
        const href = typeof a.href === 'string' ? a.href : a.getAttribute('href');
        let u;
        try { u = new URL(href, location.href); } catch (err) { return null; }
        const here = new URL(location.href);
        if (u.origin === here.origin && u.pathname === here.pathname && u.search === here.search) return null;
        return { event: e, to: recPageKey(u.href) };
    }

    function recLeave() {
        if (!recording) return;
        const went = recLink && !recLink.event.defaultPrevented ? recLink.to : null;
        recSave(went);
    }

    function recNavigation() {
        try {
            const entry = performance.getEntriesByType('navigation')[0];
            return entry && entry.type ? entry.type : 'navigate';
        } catch (e) { return 'navigate'; }
    }

    /* Whether the person was somewhere the recorder could not see, between
       the last page it ran on and this one. A page without the engine shows no
       bar and nothing on it can say it is not recording, so the next page that
       can, says it. Worded so it is true however the gap came about: a link
       that redirected is also a page the recorder did not run on. It names
       no page it did not see: the person has just come back from it, and no
       address goes into a recording. `here` and the saved ones are page keys. */
    function recGap(saved, here, nav) {
        const last = saved.at;
        if (saved.heading && saved.heading !== here) {
            return 'The last click led to a page the recorder does not run on, so anything done '
                 + 'there was not recorded.';
        }
        if (saved.heading || nav === 'reload') return null;
        const from = nav !== 'back_forward' && document.referrer ? recPageKey(document.referrer) : null;
        if (from) {
            return from === last || from === here ? null
                 : 'You came here from a page the recorder does not run on, so anything done '
                   + 'there was not recorded.';
        }
        if (nav === 'back_forward') {
            return here !== last ? null
                 : 'You came back to this page. If you were on a page the recorder does not '
                   + 'run on, anything done there was not recorded.';
        }
        return here === last ? null
             : 'The recorder cannot tell how you got here from ' + recPageName(last) + '. If you '
               + 'went through a page it does not run on, anything done there was not recorded.';
    }

    /* The bar, the listeners, and the frame poll, for a recording that is
       starting or being taken up. */
    function recOpen() {
        if (active) end('recording');
        recording = true;
        recLast = null;
        recLink = null;
        recBar();
        recUi.bar.hidden = false;
        recUi.out.hidden = true;
        recUi.out.textContent = '';
        listenTo(document);
        // The frame arrives when My Time is opened, which is usually DURING the
        // recording, so it is picked up on the poll rather than once at the start.
        if (!recPoll) {
            recPoll = setInterval(function () {
                const f = frameReady();
                if (f) listenTo(f.doc);
            }, REC.pollMs);
        }
        const f = frameReady();
        if (f) listenTo(f.doc);
    }

    /* A recording under way, taken up by this page. Read from STORAGE, never
       from memory: a page back from the back-forward cache holds the list as
       it was when it was left, and the pages since may have added to it. */
    function recArrive(how) {
        return;   // RECORDER DISABLED in this build (tools/vendor_tour.py)
        const saved = recSaved();
        if (!saved) {
            if (recording) recEndHere();              // it was stopped on another page
            return;
        }
        const nav = how === 'cache' ? 'back_forward' : recNavigation();
        recSteps = saved.steps;
        recReview = saved.review;
        recPages = Array.isArray(saved.pages) ? saved.pages : [];
        const gap = recGap(saved, recPageKey(location.href), nav);
        const here = recPage();
        if (gap) recReview.push({ step: null, title: null, page: here, why: [gap] });
        if (nav === 'back_forward') {
            recReview.push({ step: null, title: null, page: here, why: [
                'Back or Forward was used to reach ' + here + ' after step ' + recSteps.length
                + '. A tour cannot press Back for anyone, so the next step has to say it'] });
        }
        recOpen();
        const n = recSteps.length;
        // Taken up, never started over, so the way to start over is said: a
        // recording left without Stop comes back in this tab otherwise.
        recNotice('Still recording: ' + n + (n === 1 ? ' step' : ' steps') + ' so far.'
                  + (gap ? ' ' + gap : '') + ' Press Stop to end it and start another.');
        recChanged();
        console.info('[tour] recording taken up on this page, ' + n + ' steps so far');
    }

    // Stopped on another page: this one lets go too, and hands nothing over.
    function recEndHere() {
        recording = false;
        if (recPoll) { clearInterval(recPoll); recPoll = null; }
        stopListening();
        if (recUi) recUi.bar.hidden = true;
    }

    function recStart() {
        return;   // RECORDER DISABLED in this build (tools/vendor_tour.py)
        if (recording) return;
        // A recording under way is taken up, never started over: ?tour=record
        // stays in the address bar through a reload and a Back.
        if (recSaved()) return recArrive('load');
        recSteps = [];
        recReview = [];
        recPages = [];
        recOpen();
        recPage();                                    // where it starts is page 1
        recNotice('');
        recChanged();
        console.info('[tour] recording: do the task once, then press Stop');
    }

    function recHeadline(steps, review) {
        const n = steps.length;
        const count = function (w) { return review.filter(function (r) { return r.words === w; }).length; };
        const unchecked = count('unchecked');
        const withheld = count('withheld');
        let text = n + (n === 1 ? ' step' : ' steps') + ' recorded. Every one needs a person to write its words.';
        if (unchecked) {
            text += ' ' + unchecked + (unchecked === 1 ? ' of them is' : ' of them are')
                  + ' named with words taken off the page that could not be checked: the recorder'
                  + ' cannot tell a customer\'s or a colleague\'s name from a button\'s label, so read'
                  + ' every title before you send this.';
        }
        if (withheld) {
            text += ' ' + withheld + (withheld === 1 ? ' had its words' : ' had their words')
                  + ' withheld, and ' + (withheld === 1 ? 'is' : 'are') + ' called by what '
                  + (withheld === 1 ? 'it is.' : 'they are.');
        }
        // No address is kept, so the numbers that stand in for them are said.
        if (n) {
            text += ' Pages are numbered in the order the recording reached them, and no part of'
                  + ' any address is kept.';
        }
        return text + ' Copy this and send it to whoever looks after the tour.';
    }

    /* Handed over only after the same refusal rules a host's steps face. A
       recording that would be refused at mount is a bug in here, not something
       for the person who pressed Record to work out, so it is reported as one. */
    function recStop() {
        if (!recording) return null;
        recording = false;
        recForget();
        if (recPoll) { clearInterval(recPoll); recPoll = null; }
        stopListening();
        const steps = recSteps.slice();
        const problems = stepProblems(steps, { frame: true });
        const dump = { steps: steps, review: recReview.slice(), problems: problems };
        recDump = dump;
        const text = JSON.stringify({ steps: steps, review: dump.review }, null, 2);
        if (recUi) {
            recUi.bar.hidden = true;
            recUi.out.hidden = false;
            recUi.out.textContent = '';
            const head = document.createElement('p');
            head.className = 'tour-rec__head';
            head.textContent = recHeadline(steps, dump.review);
            const box = document.createElement('textarea');
            box.className = 'tour-rec__text';
            box.readOnly = true;
            box.value = text;
            const close = document.createElement('button');
            close.type = 'button';
            close.className = 'tour-rec__close';
            close.setAttribute('data-tour-rec', 'close');
            close.textContent = 'Close';
            close.addEventListener('click', function () { recUi.out.hidden = true; });
            recUi.out.appendChild(head);
            recUi.out.appendChild(box);
            recUi.out.appendChild(close);
            box.focus();
            box.select();
        }
        if (problems.length) {
            console.error('[tour] the recorder produced a step list the engine would refuse. '
                          + 'This is a fault in the recorder:', problems);
        }
        console.info('[tour] recording stopped:', steps.length, 'steps,',
                     dump.review.length, 'notes for review');
        return dump;
    }

    /* ── Lifecycle ─────────────────────────────────────────────────────────── */
    function start(custom, opts) {
        /* NOT BEFORE THE MOUNT, which is where the host is read. A start that
           came earlier would run the built-in tour on a page that has a
           TourHost it has not seen yet. */
        if (!mounted) {
            if (!hostRefused) console.warn('[tour] not starting before the page has loaded');
            else console.error('[tour] not starting: TourHost was refused, see above');
            return;
        }
        /* NOTHING IS DRAWN UNSTYLED. On the <link> fallback the rules can still
           be on their way, and without them the overlay is an unpositioned
           spotlight and a card at the foot of the page. A start that arrives
           early waits; one that arrives after the stylesheet failed does
           nothing and says so. Only the LATEST early request is kept, so the
           resume poll asking every second does not queue a start per second. */
        if (!stylesReady) {
            if (stylesFailed) {
                console.error('[tour] not starting: the tour stylesheet did not load');
                return;
            }
            const first = !deferredStart;
            deferredStart = [custom, opts];
            if (first) {
                installStyles().then(function (ok) {
                    const args = deferredStart;
                    deferredStart = null;
                    if (ok && args) start(args[0], args[1]);
                });
            }
            return;
        }
        if (active) end('restart');
        if (!ready()) {
            console.warn('[tour] nothing to show until the page is ready');
            return;
        }
        opts = opts || {};
        tourId = opts.id || 'default';
        steps = (custom || (host ? host.steps : STEPS))
            .map(function (s, i) { return Object.assign({}, s, { origin: i }); });
        active = true;
        timedOut = false;
        shownTarget = false;
        listenTo(document);
        build();
        const t = rectOf({ el: trigger, doc: document, frameEl: null });
        lastCenter = null;
        if (t) { moveCursor(centerOf(t), false); ui.cursor.hidden = false; }
        lastCenter = t ? centerOf(t) : null;
        tickTimer = setInterval(tick, 250);
        trigger.setAttribute('aria-expanded', 'true');
        show(typeof opts.index === 'number' ? opts.index : 0);
    }

    function end(reason) {
        deferredStart = null;              // a start still waiting on the rules is cancelled too
        if (!active) return;
        active = false;
        runToken++;
        current = -1;
        lastCenter = null;
        travelUntil = 0;
        placedIndex = -1;
        clearTimeout(waitTimer);
        clearInterval(tickTimer);
        if (frameReq) { cancelAnimationFrame(frameReq); frameReq = 0; }
        stopListening();
        if (ui) {
            ui.spot.remove();
            ui.cursor.remove();
            ui.tip.remove();
            ui.chip.remove();
            ui = null;
        }
        steps = [];
        timedOut = false;
        clearResume();
        if (trigger) {
            trigger.setAttribute('aria-expanded', 'false');
            if (reason !== 'restart') trigger.focus({ preventScroll: true });
        }
    }

    function mountTrigger() {
        // Read here rather than when this file runs, so a host script placed
        // after this one is still seen on a page that is still loading.
        if (!readHost()) return;               // refused: no trigger, no listeners
        const styled = installStyles();
        trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'tour-trigger';
        trigger.setAttribute('data-tour-trigger', '');
        trigger.setAttribute('aria-expanded', 'false');
        trigger.textContent = 'How to use this page';
        trigger.hidden = !(ready() && stylesReady);
        trigger.addEventListener('click', function () { start(); });
        document.body.appendChild(trigger);
        mounted = true;
        // Shown the moment the rules land, not at the next readiness poll.
        styled.then(function () { trigger.hidden = !(ready() && stylesReady); });
        watchTabs();

        /* A page load in the middle of a tour is a real case here: the tour
           crosses between /manager and /. The step index is already in
           sessionStorage, so this is only picking it back up.

           NOT one attempt at DOMContentLoaded. The dashboard sits behind a
           login overlay until an async session check finishes, so readiness is
           false for the first moment of every load on /manager and a one-shot
           resume never fired there. It fired on / only because that page has no
           such gate, which is exactly the kind of difference that makes a bug
           look like it works. */
        // At least as long as a host allows for its first target: see "The host".
        let resumeUntil = Date.now() + Math.max(15000, (host && host.timeouts.firstTargetMs) || 0);
        function tryResume() {
            if (active || Date.now() > resumeUntil) return;
            const at = pendingResume();
            if (at === null) { resumeUntil = 0; return; }
            if (ready()) start(null, { index: at });
        }
        tryResume();
        /* Record mode without a console, for the person who is going to author
           the tour: ?tour=record in the address bar. It waits for the page to
           be ready the same way the trigger does, because a recording started
           on the login screen would have nothing to point at.

           A recording already under way is taken up the moment this page can
           show it, not at the next poll: a person who clicks as soon as the page
           appears is recording again already. */
        const wantsRecord = false;   // RECORDER DISABLED in this build (tools/vendor_tour.py)
        let fromCache = false;         // back from the cache, and not taken up yet
        function tryRecord() {
            if (recording || !ready() || !stylesReady) return;
            if (recSaved()) recArrive(fromCache ? 'cache' : 'load');
            else if (wantsRecord && !recUi) recStart();
            fromCache = false;
        }
        tryRecord();
        styled.then(tryRecord);
        window.addEventListener('pagehide', recLeave);
        /* BACK FROM THE CACHE: no load, no mount, and a list in memory that is
           the one this page held when it was left. A page that was recording
           reads storage AT ONCE, ready or not. Waiting for ready is for a page
           starting on a sign-in screen, and here it meant waiting forever: the
           poll skips a page that is already recording, so a page that re-checked
           its session on the way back kept its stale list, and Stop handed it
           over short. The review found it. A page that was not recording is
           taken up by the poll once it is ready, as any page is. */
        window.addEventListener('pageshow', function (e) {
            if (!e.persisted) return;
            if (recording) return recArrive('cache');
            fromCache = true;
            tryRecord();
        });
        setInterval(function () {
            const isReady = ready();
            trigger.hidden = !(isReady && stylesReady);
            if (!isReady && active) end('signed-out');
            tryRecord();
            tryResume();
        }, 1000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mountTrigger);
    } else {
        mountTrigger();
    }

    global.Tour = {
        start: start,
        end: function () { end('api'); },
        // Record mode. Also reachable without a console: ?tour=record.
        record: function () { return null; },   // RECORDER DISABLED in this build (tools/vendor_tour.py)
        stopRecording: recStop,
        // What the last Stop handed over, however it was pressed.
        lastRecording: function () { return recDump; },
        recording: function () { return { on: recording, steps: recSteps.length }; },
        // Selectors and counters only, never page content.
        state: function () {
            const s = current >= 0 ? steps[current] : null;
            return { active: active, index: current, total: steps.length,
                     sel: s ? describeTarget(s) : null,
                     foundBy: s ? foundBy : null,
                     kind: s ? (s.kind || 'step') : null,
                     expanding: !!(s && s.expandFor),
                     guidingTab: s ? (s.tabGuide || null) : null,
                     timedOut: timedOut,
                     activeTab: activeTabName,
                     tabErrors: tabErrors };
        },
    };

    /* tour.css:begin -- GENERATED by scripts/sync_tour_css.py from
       tour.css. Do not edit here: edit tour.css and run the
       script. tests/check_tour_csp.py fails if the two differ.
       A function declaration, so it is hoisted and can sit at the end. */
    function tourCss() {
        return [
            "/* \u2500\u2500 Guided tour engine styles \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
            " * Self-contained: nothing here reads the app's own tokens. Every rule is scoped",
            " * to a tour- class.",
            " *",
            " * THIS FILE IS THE SOURCE, AND A PAGE DOES NOT LINK IT. tour.js adopts these",
            " * rules as a constructable stylesheet, so a host needs one <script> tag. They",
            " * are embedded in tour.js verbatim by scripts/sync_tour_css.py: edit here, then",
            " * run it. tests/check_tour_csp.py fails while the two differ. This file is also",
            " * what the engine links itself for a browser without constructable sheets.",
            " *",
            " * Layers, bottom to top: page, trigger, spotlight (with the dimming shadow),",
            " * cursor, card. All above the app's highest z-index (9999). The spotlight",
            " * ignores the pointer, so the real element under it stays clickable.",
            " */",
            ":root {",
            "    --tour-surface:    #161B22;",
            "    --tour-border:     #30363D;",
            "    --tour-text:       #E6EDF3;",
            "    --tour-muted:      #9DA7B3;",
            "    --tour-accent:     #58A6FF;",
            "    --tour-accent-ink: #0D1117;",
            "    --tour-dim:        rgba(0, 0, 0, 0.55);",
            "}",
            "",
            ".tour-trigger,",
            ".tour-tip {",
            "    box-sizing: border-box;",
            "    font-family: inherit;",
            "}",
            "",
            "/* \u2500\u2500 Trigger \u2500\u2500 */",
            ".tour-trigger {",
            "    position: fixed;",
            "    right: 20px;",
            "    bottom: 20px;",
            "    z-index: 2147483000;",
            "    padding: 10px 16px;",
            "    border-radius: 999px;",
            "    border: 1px solid var(--tour-border);",
            "    background: var(--tour-surface);",
            "    color: var(--tour-text);",
            "    font-size: 0.875rem;",
            "    font-weight: 600;",
            "    cursor: pointer;",
            "    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);",
            "}",
            "/* A class sets display, which would otherwise beat the hidden attribute. */",
            ".tour-trigger[hidden] { display: none; }",
            ".tour-trigger:hover   { border-color: var(--tour-accent); }",
            "",
            ".tour-trigger:focus-visible,",
            ".tour-tip button:focus-visible {",
            "    outline: 2px solid var(--tour-accent);",
            "    outline-offset: 2px;",
            "}",
            "",
            "/* \u2500\u2500 Spotlight \u2500\u2500 */",
            ".tour-spot {",
            "    position: fixed;",
            "    left: 0;",
            "    top: 0;",
            "    z-index: 2147483001;",
            "    border-radius: 8px;",
            "    pointer-events: none;",
            "    box-shadow: 0 0 0 2px var(--tour-accent), 0 0 0 9999px var(--tour-dim);",
            "    transition: left 0.2s ease, top 0.2s ease, width 0.2s ease, height 0.2s ease;",
            "}",
            ".tour-spot[hidden],",
            ".tour-cursor[hidden] { display: none; }",
            "",
            "/* \u2500\u2500 Ghost cursor \u2500\u2500 */",
            ".tour-cursor {",
            "    position: fixed;",
            "    left: 0;",
            "    top: 0;",
            "    z-index: 2147483002;",
            "    width: 22px;",
            "    height: 22px;",
            "    pointer-events: none;",
            "    transition: transform 0.6s cubic-bezier(0.4, 0, 0.2, 1);",
            "    will-change: transform;",
            "}",
            ".tour-cursor svg {",
            "    display: block;",
            "    width: 22px;",
            "    height: 22px;",
            "    filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.6));",
            "}",
            "/* The pulse ring is centred on the arrow's tip, which is the element's centre. */",
            ".tour-cursor::after {",
            "    content: '';",
            "    position: absolute;",
            "    left: -9px;",
            "    top: -9px;",
            "    width: 18px;",
            "    height: 18px;",
            "    border-radius: 50%;",
            "    border: 2px solid var(--tour-accent);",
            "    opacity: 0;",
            "    pointer-events: none;",
            "}",
            ".tour-cursor--pulse::after { animation: tour-pulse 0.7s ease-out 1; }",
            ".tour-cursor--fade         { animation: tour-fade 0.25s ease-out 1; }",
            "",
            "@keyframes tour-pulse {",
            "    0%   { opacity: 0.9; transform: scale(0.4); }",
            "    100% { opacity: 0;   transform: scale(1.8); }",
            "}",
            "@keyframes tour-fade {",
            "    from { opacity: 0; }",
            "    to   { opacity: 1; }",
            "}",
            "",
            "/* \u2500\u2500 Card \u2500\u2500 */",
            ".tour-tip {",
            "    position: fixed;",
            "    left: 0;",
            "    top: 0;",
            "    z-index: 2147483003;",
            "    width: min(320px, calc(100vw - 16px));",
            "    padding: 14px 16px 12px;",
            "    border-radius: 10px;",
            "    background: var(--tour-surface);",
            "    border: 1px solid var(--tour-border);",
            "    color: var(--tour-text);",
            "    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);",
            "    outline: none;",
            "}",
            "/* Nothing to point at: the card is docked. WHERE is decided in tour.js, not",
            "   here. It used to be fixed at right 20px, bottom 72px with !important, which",
            "   put it on top of whatever the page had there. placeCard() now starts from",
            "   that corner and moves the card wherever a control has to stay clickable.",
            "   The class stays as a marker for the state, with nothing of its own. */",
            ".tour-tip--docked {}",
            ".tour-tip__title {",
            "    margin: 0 0 6px;",
            "    font-size: 0.95rem;",
            "    font-weight: 700;",
            "    color: var(--tour-text);",
            "}",
            ".tour-tip__body {",
            "    margin: 0 0 12px;",
            "    font-size: 0.85rem;",
            "    line-height: 1.45;",
            "    color: var(--tour-text);",
            "}",
            ".tour-tip__foot {",
            "    display: flex;",
            "    align-items: center;",
            "    gap: 8px;",
            "}",
            ".tour-tip__progress {",
            "    margin-right: auto;",
            "    font-size: 0.75rem;",
            "    color: var(--tour-muted);",
            "}",
            ".tour-tip button {",
            "    font: inherit;",
            "    font-size: 0.8rem;",
            "    padding: 6px 12px;",
            "    border-radius: 6px;",
            "    cursor: pointer;",
            "}",
            ".tour-btn-skip,",
            ".tour-btn-end {",
            "    background: transparent;",
            "    color: var(--tour-muted);",
            "    border: 1px solid var(--tour-border);",
            "}",
            ".tour-btn-next {",
            "    background: var(--tour-accent);",
            "    color: var(--tour-accent-ink);",
            "    border: 1px solid var(--tour-accent);",
            "    font-weight: 600;",
            "}",
            "",
            "/* Snap and fade instead of travel and pulse. */",
            "@media (prefers-reduced-motion: reduce) {",
            "    .tour-spot,",
            "    .tour-cursor { transition: none; }",
            "    .tour-cursor--pulse::after { animation: none; }",
            "}",
            "",
            "/* The target went away: a modal closed, a tab changed. Small, out of the way,",
            "   and one click back into the tour. */",
            ".tour-chip {",
            "    position: fixed;",
            "    right: 20px;",
            "    bottom: 72px;",
            "    z-index: 2147483003;",
            "    padding: 8px 14px;",
            "    border-radius: 999px;",
            "    border: 1px solid var(--tour-accent);",
            "    background: var(--tour-surface);",
            "    color: var(--tour-accent);",
            "    font: inherit;",
            "    font-size: 0.8rem;",
            "    font-weight: 600;",
            "    cursor: pointer;",
            "    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);",
            "}",
            ".tour-chip[hidden] { display: none; }",
            "",
            "/* ---- Record mode -------------------------------------------------------- ",
            "   The bar a person watches while recording, and the panel the step list comes",
            "   out in. Both are tour UI, so clicks on them are never recorded. */",
            ".tour-rec {",
            "    position: fixed;",
            "    left: 20px;",
            "    bottom: 20px;",
            "    z-index: 2147483004;",
            "    display: flex;",
            "    align-items: center;",
            "    gap: 10px;",
            "    padding: 8px 14px;",
            "    border-radius: 999px;",
            "    border: 1px solid var(--tour-accent);",
            "    background: var(--tour-surface);",
            "    color: var(--tour-text);",
            "    font: inherit;",
            "    font-size: 0.8rem;",
            "    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);",
            "}",
            ".tour-rec[hidden] { display: none; }",
            ".tour-rec__dot {",
            "    width: 10px;",
            "    height: 10px;",
            "    border-radius: 50%;",
            "    background: #f85149;",
            "}",
            ".tour-rec__count { font-weight: 600; }",
            "/* What a page load did to the recording: taken up, and anywhere it could not see. */",
            ".tour-rec__note { max-width: 420px; line-height: 1.35; }",
            ".tour-rec__stop {",
            "    font: inherit;",
            "    font-size: 0.75rem;",
            "    font-weight: 600;",
            "    padding: 3px 10px;",
            "    border-radius: 6px;",
            "    border: 1px solid var(--tour-border);",
            "    background: transparent;",
            "    color: var(--tour-text);",
            "    cursor: pointer;",
            "}",
            "",
            "/* The step list, where a person can select it and copy it out. */",
            ".tour-rec__out {",
            "    position: fixed;",
            "    left: 20px;",
            "    bottom: 20px;",
            "    z-index: 2147483004;",
            "    width: min(560px, calc(100vw - 40px));",
            "    display: flex;",
            "    flex-direction: column;",
            "    gap: 8px;",
            "    padding: 14px;",
            "    border-radius: 10px;",
            "    border: 1px solid var(--tour-border);",
            "    background: var(--tour-surface);",
            "    color: var(--tour-text);",
            "    font: inherit;",
            "    font-size: 0.8rem;",
            "    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);",
            "}",
            ".tour-rec__out[hidden] { display: none; }",
            ".tour-rec__head { margin: 0; color: var(--tour-muted); }",
            ".tour-rec__text {",
            "    width: 100%;",
            "    height: 220px;",
            "    resize: vertical;",
            "    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;",
            "    font-size: 0.72rem;",
            "    line-height: 1.45;",
            "    padding: 8px;",
            "    border-radius: 6px;",
            "    border: 1px solid var(--tour-border);",
            "    background: #0D1117;",
            "    color: var(--tour-text);",
            "}",
            ".tour-rec__close {",
            "    align-self: flex-end;",
            "    font: inherit;",
            "    font-size: 0.75rem;",
            "    font-weight: 600;",
            "    padding: 4px 12px;",
            "    border-radius: 6px;",
            "    border: 1px solid var(--tour-border);",
            "    background: transparent;",
            "    color: var(--tour-text);",
            "    cursor: pointer;",
            "}",
        ].join('\n');
    }
    /* tour.css:end */
})(window);
