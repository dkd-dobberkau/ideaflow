// Load nostr-tools dynamically
let nostrTools = null;
(async () => {
    nostrTools = await import('https://esm.sh/nostr-tools@2.1.0');
    window.NostrTools = nostrTools;
})();

function ideaFlow() {
    return {
        pubkey: null,
        privateKey: null,
        newIdea: '',
        activeTab: 'ideas',
        isSubmitting: false,
        submitStatus: null,
        graph: null,
        nostrReady: false,

        async init() {
            const stored = localStorage.getItem('nostr_keys');
            if (stored) {
                const keys = JSON.parse(stored);
                this.pubkey = keys.pubkey;
                this.privateKey = keys.privateKey;
            }

            this.$watch('activeTab', (tab) => {
                if (tab === 'network') {
                    this.$nextTick(() => this.loadNetworkGraph());
                }
            });

            // Wait for nostr-tools to load
            while (!window.NostrTools) {
                await new Promise(r => setTimeout(r, 100));
            }
            this.nostrReady = true;
        },

        async generateKeys() {
            if (!window.NostrTools) {
                await new Promise(r => setTimeout(r, 500));
                if (!window.NostrTools) {
                    console.error('NostrTools not loaded');
                    return;
                }
            }
            const sk = window.NostrTools.generateSecretKey();
            const pk = window.NostrTools.getPublicKey(sk);

            // Convert Uint8Array to hex string
            this.privateKey = Array.from(sk).map(b => b.toString(16).padStart(2, '0')).join('');
            this.pubkey = pk;

            localStorage.setItem('nostr_keys', JSON.stringify({
                pubkey: this.pubkey,
                privateKey: this.privateKey
            }));
        },

        async submitIdea() {
            if (!this.newIdea.trim() || !this.pubkey) return;
            if (!window.NostrTools || !window.NostrTools.finalizeEvent) {
                console.error('NostrTools not ready');
                return;
            }

            this.isSubmitting = true;
            this.submitStatus = null;

            // Convert hex string to Uint8Array
            const skBytes = new Uint8Array(this.privateKey.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));

            const eventTemplate = {
                kind: 30023,
                created_at: Math.floor(Date.now() / 1000),
                tags: [
                    ['d', crypto.randomUUID()],
                    ['t', 'idea'],
                    ['client', 'ideaflow']
                ],
                content: this.newIdea
            };

            // finalizeEvent adds id, pubkey, and sig
            const event = window.NostrTools.finalizeEvent(eventTemplate, skBytes);

            try {
                const response = await fetch('/api/ideas', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(event)
                });

                if (response.ok) {
                    this.newIdea = '';
                    this.submitStatus = 'ok';
                    setTimeout(() => { this.submitStatus = null; }, 2000);

                    htmx.ajax('GET', '/partials/recent-ideas', {target: '#idea-stream > div:last-child', swap: 'innerHTML'});
                } else {
                    this.submitStatus = 'error';
                }
            } catch (e) {
                console.error('Submit error:', e);
                this.submitStatus = 'error';
            } finally {
                this.isSubmitting = false;
            }
        },

        async loadNetworkGraph() {
            const container = document.getElementById('network-graph');
            if (!container) return;

            try {
                const response = await fetch('/api/network-data');
                const data = await response.json();

                if (data.nodes.length === 0) {
                    container.innerHTML = '<p class="text-gray-500 text-center p-8">Noch keine Ideen für das Netzwerk vorhanden</p>';
                    return;
                }

                data.nodes.forEach(node => {
                    node.isOwn = node.pubkey === this.pubkey;
                });

                if (this.graph) {
                    this.graph.graphData(data);
                } else {
                    this.graph = ForceGraph()(container)
                        .graphData(data)
                        .nodeLabel('content_preview')
                        .nodeColor(node => node.isOwn ? '#3b82f6' : '#9ca3af')
                        .nodeRelSize(6)
                        .linkColor(() => '#e5e7eb')
                        .linkWidth(1)
                        .onNodeClick(node => {
                            htmx.ajax('GET', `/components/idea-card/${node.id}`, {target: '#idea-detail', swap: 'innerHTML'});
                            this.activeTab = 'ideas';
                        })
                        .width(container.clientWidth)
                        .height(600);
                }
            } catch (e) {
                console.error('Network graph error:', e);
                container.innerHTML = '<p class="text-red-500 text-center p-8">Fehler beim Laden des Netzwerks</p>';
            }
        }
    }
}

function renderClusters(event) {
    const container = document.getElementById('clusters-container');
    if (!container) return;

    try {
        const data = JSON.parse(event.detail.xhr.response);

        if (!data.clusters || data.clusters.length === 0) {
            container.innerHTML = '<p class="text-gray-500 text-center p-8">Noch nicht genug Ideen für Cluster-Analyse (mindestens 5 benötigt)</p>';
            return;
        }

        let html = '';
        data.clusters.forEach((cluster, index) => {
            html += `
                <div class="cluster-card">
                    <h3>Cluster ${index + 1} (${cluster.length} Ideen)</h3>
                    <div class="ideas-list">
                        ${cluster.map(idea => `
                            <div class="idea-item cursor-pointer"
                                 hx-get="/components/idea-card/${idea.event_id}"
                                 hx-target="#idea-detail"
                                 hx-swap="innerHTML"
                                 onclick="document.querySelector('[x-data]').__x.$data.activeTab = 'ideas'">
                                ${idea.content_preview}
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
        htmx.process(container);
    } catch (e) {
        console.error('Clusters render error:', e);
        container.innerHTML = '<p class="text-red-500 text-center p-8">Fehler beim Laden der Cluster</p>';
    }
}
