import { Alert } from 'react-native';
import api from '../api/client';
import { usePlayerStore } from '../stores/usePlayerStore';
import { useStationsStore } from '../stores/useStationsStore';
import { registerPlayer, releaseCurrent } from './audioController';
import { updateNowPlaying } from './nativePlayerBridge';

let createAudioPlayer: any;
try {
  createAudioPlayer = require('expo-audio').createAudioPlayer;
} catch {}

export interface PlayableStation {
  id: string;
  name: string;
  favicon?: string | null;
  logo_url?: string | null;
  country?: string | null;
  language?: string | null;
  source?: string;
  is_flagship?: boolean;
  stream_url?: string | null;
}

/**
 * Resolve + start a live imported radio stream (shared by All Stations and Listen).
 * Returns true when a stream actually started playing.
 */
export async function playImportedStation(st: PlayableStation, router: any): Promise<boolean> {
  if (!createAudioPlayer) {
    Alert.alert('Audio', 'Audio module not available in this preview.');
    return false;
  }
  const P = usePlayerStore.getState();
  try {
    const r = await api.post(`/radio/play/${st.id}`);
    const data = r.data || {};
    const streamUrl = data.stream_url || st.stream_url;
    if (data.mode === 'ai' && data.channel_slug) {
      router.push({ pathname: '/(tabs)/radio', params: { channel: data.channel_slug } });
      return false;
    }
    if (!streamUrl) {
      Alert.alert('Unavailable', 'This station has no playable stream right now.');
      return false;
    }
    releaseCurrent();
    P.setSession(null);
    const player = createAudioPlayer(streamUrl);
    registerPlayer(player);
    player.play();
    const subtitle = [data.country || st.country, data.language || st.language]
      .filter(Boolean).join(' · ') || 'Live radio';
    P.setActiveChannel(st.id, data.name || st.name, st.favicon || st.logo_url || null);
    P.setCurrentSeg({
      segment_id: st.id,
      segment_url: '',
      track_title: data.name || st.name,
      track_artist: subtitle,
      channel_name: data.name || st.name,
    });
    P.setPlaying(true);
    useStationsStore.getState().addRecent({
      id: st.id, name: data.name || st.name, favicon: st.favicon, logo_url: st.logo_url,
      country: st.country, language: st.language, source: st.source, is_flagship: st.is_flagship,
    });
    updateNowPlaying(streamUrl, data.name || st.name, subtitle, data.name || st.name, null);
    return true;
  } catch {
    Alert.alert('Error', 'Could not play this station. Try another.');
    return false;
  }
}
