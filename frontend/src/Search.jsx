// Phase 15b — federated search placeholder. Real search lands later.
// Reads ?q= and shows the query + a friendly stub so the TopbarSearch
// shortcut has a meaningful destination.
import React from "react";
import { useSearchParams, Link } from "react-router-dom";
import { Search as SearchIcon } from "lucide-react";
import { Card, Button, Chip } from "@/shell/primitives";

export default function Search() {
  const [params] = useSearchParams();
  const q = (params.get("q") || "").trim();
  return (
    <div data-testid="search-root" className="max-w-3xl mx-auto py-8 space-y-6">
      <div className="text-[10px] font-mono uppercase tracking-widest
                            text-text-secondary flex items-center gap-2">
        <SearchIcon size={12} /> search · phase 15b stub
      </div>
      <h1 className="font-display font-bold text-4xl tracking-display-tight">
        {q ? <>Searching for <span className="text-accent-electric">“{q}”</span></>
                : <>What are you looking for?</>}
      </h1>
      <Card className="p-6 space-y-3">
        <div className="text-sm text-text-secondary">
          Federated search across stations, shows, games, and venues will
          go live alongside the recommendations engine.
        </div>
        <div className="flex flex-wrap gap-2">
          <Chip tone="electric">stations</Chip>
          <Chip tone="electric">shows</Chip>
          <Chip tone="gold">games</Chip>
          <Chip>venues</Chip>
          <Chip>passport</Chip>
        </div>
        <div className="flex gap-3 pt-2">
          <Link to="/"><Button variant="ghost" size="sm">Go home</Button></Link>
          <Link to="/radio"><Button size="sm">Open radio</Button></Link>
        </div>
      </Card>
    </div>
  );
}
