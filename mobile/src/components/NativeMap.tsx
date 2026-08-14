// Native-only map wrapper. Metro picks NativeMap.web.tsx on web (a no-op stub),
// so react-native-maps is never bundled for the web preview.
import React from 'react';
import { StyleSheet } from 'react-native';
import MapView, { Marker } from 'react-native-maps';

export const MAPS_AVAILABLE = true;

export type MapPin = {
  id: string; lat: number; lng: number;
  title?: string; description?: string; onPress?: () => void;
};

type Props = {
  region: { latitude: number; longitude: number; latitudeDelta: number; longitudeDelta: number };
  markers?: MapPin[];
  showsUserLocation?: boolean;
  interactive?: boolean;
};

export default function NativeMap({ region, markers = [], showsUserLocation, interactive = true }: Props) {
  return (
    <MapView
      style={StyleSheet.absoluteFill}
      initialRegion={region}
      showsUserLocation={showsUserLocation}
      pointerEvents={interactive ? 'auto' : 'none'}
    >
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
