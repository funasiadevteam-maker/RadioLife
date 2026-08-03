// Phase MER.4 — Saved businesses list.
import React from "react";
import { Bookmark } from "lucide-react";
import { RelationList } from "./_RelationList";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function MeSaved() {
  return <RelationList
    testid="me-saved"
    endpoint={`${API}/me/saved-businesses`}
    title="Saved Businesses"
    emptyLabel="You haven't saved any business yet."
    icon={<Bookmark size={30}/>}/>;
}
