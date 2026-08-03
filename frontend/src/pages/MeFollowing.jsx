// Phase MER.4 — Followed businesses list.
import React from "react";
import { Heart } from "lucide-react";
import { RelationList } from "./_RelationList";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function MeFollowing() {
  return <RelationList
    testid="me-following"
    endpoint={`${API}/me/followed-businesses`}
    title="Following"
    emptyLabel="You're not following any business yet."
    icon={<Heart size={30}/>}/>;
}
