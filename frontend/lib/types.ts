export type Evidence = {
  id: string; category: string; source: string; observed_at: string; value: string;
  confidence: "observed" | "inferred" | "unknown";
};
export type Provider = {
  id: string; name: string; roles: string[]; evidence_ids: string[]; confidence: "observed" | "inferred";
};
export type Location = {
  ip: string; country: string; latitude: number; longitude: number; source: string; label: string;
};
export type CategoryScore = { name: string; score: number | null; explanation: string; evidence_ids: string[] };
export type Intelligence = {
  domain: string; collected_at: string; mode: "live" | "demo"; dns: Record<string, string[]>;
  dnssec_validated: boolean | null; addresses: string[]; headers: Record<string, string>;
  tls: { issuer: string; subject: string; not_after: string; days_remaining: number; protocol: string; fingerprint: string; verified: boolean } | null;
  providers: Provider[]; locations: Location[]; evidence: Evidence[]; warnings: string[];
  scores: CategoryScore[]; overall_score: number | null; coverage: number;
};
export type Snapshot = { id: string; domain: string; created_at: string; intelligence: Intelligence; changes: string[] };
export type GraphNode = { id: string; label: string; kind: "domain" | "provider" | "ip" | "asn"; detail: string; provider_id?: string };
export type GraphEdge = { id: string; source: string; target: string; label: string; confidence: string; evidence_ids: string[] };
export type Portfolio = {
  asset_count: number;
  providers: { id: string; name: string; assets: string[]; roles: string[]; concentration: number }[];
  leaderboard: { domain: string; score: number | null; coverage: number; providers: number; mode: string }[];
  scope: string;
};
export type Workspace = { snapshots: Snapshot[]; portfolio: Portfolio; graph: { nodes: GraphNode[]; edges: GraphEdge[] }; mode: "demo" | "live" };
export type Simulation = {
  provider: string; provider_id: string; affected_assets: string[]; affected_node_ids: string[];
  concentration: number; interpretation: string;
};
export type ScanJob = { id: string; domain: string; status: "queued" | "running" | "completed" | "failed"; error: string | null };
export type AnalystAnswer = { mode: string; answer: string; citations: Evidence[] };
