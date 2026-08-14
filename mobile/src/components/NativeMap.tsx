// Native-only map wrapper. Metro picks NativeMap.web.tsx on web (a no-op stub),
// so react-native-maps is never bundled for the web preview.
import React from 'react';
import { StyleSheet } from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';

export const MAPS_AVAILABLE = true;

export type MapPin = {
  id: string; lat: number; lng: number;
  title?: string; description?: string; onPress?: () => void;
};

type Props = {
  region: { latitude: number; longitude: number; latitudeDelta: number; longitudeDelta: number };
  markers?: MapPin[];
  polyline?: { lat: number; lng: number }[];
  showsUserLocation?: boolean;
  interactive?: boolean;
};

export default function NativeMap({ region, markers = [], polyline, showsUserLocation, interactive = true }: Props) {
  return (
    <MapView
      style={StyleSheet.absoluteFill}
      initialRegion={region}
      showsUserLocation={showsUserLocation}
      pointerEvents={interactive ? 'auto' : 'none'}
    >
      {polyline && polyline.length > 1 && (
        <Polyline
          coordinates={polyline.map((p) => ({ latitude: p.lat, longitude: p.lng }))}
          strokeColor="#ea580c"
          strokeWidth={4}
        />
      )}
      {markers.map((m) => (
        <Marker
          key={m.id}
          coordinate={{ latitude: m.lat, longitude: m.lng }}
          title={m.title}
          description={m.description}
          onCalloutPress={m.onPress}
        />
      ))}
    </MapView>
  );
}
