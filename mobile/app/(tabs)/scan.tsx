import { Redirect } from 'expo-router';

// The center tab renders a raised FAB that opens the modal scanner directly,
// so this screen is normally never shown. It redirects as a safe fallback.
export default function ScanTab() {
  return <Redirect href="/scan-to-pay" />;
}
