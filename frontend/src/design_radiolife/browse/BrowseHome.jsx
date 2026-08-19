// Browse landing — fetches the shared payload, renders the selected skin.
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useBrowseLayout, useBrowseLayoutStore } from "./useBrowseLayout";
import CinematicBrowse from "./CinematicBrowse";
import StudioBrowse from "./StudioBrowse";
import TubeBrowse from "./TubeBrowse";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function BrowseHome() {
  const layout = useBrowseLayout();
  const setLayout = useBrowseLayoutStore((s) => s.setLayout);
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await axios.get(`${API}/browse/home`);
        if (alive) setData(r.data);
      } catch (_e) {
        if (alive) setData({ hero: null, rails: [] });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  const props = {
    data, loading, layout, setLayout,
    onOpen: (c) => { if (c?.href) navigate(c.href); },
  };
  if (layout === "studio") return <StudioBrowse {...props} />;
  if (layout === "tube") return <TubeBrowse {...props} />;
  return <CinematicBrowse {...props} />;
}
