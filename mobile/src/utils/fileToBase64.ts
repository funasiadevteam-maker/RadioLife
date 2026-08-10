import { Platform } from 'react-native';

/* Convert a picked file (image/PDF/spreadsheet) to a base64 string,
   cross-platform (Expo web preview + native). */
export async function uriToBase64(uri: string, webFile?: any): Promise<string> {
  // Web: prefer the File object from the picker; else fetch the uri.
  if (Platform.OS === 'web') {
    let blob: Blob;
    if (webFile) {
      blob = webFile as Blob;
    } else {
      const res = await fetch(uri);
      blob = await res.blob();
    }
    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const s = (reader.result as string) || '';
        resolve(s.includes(',') ? s.split(',')[1] : s);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }
  // Native: read the file as base64.
  try {
    const FS = await import('expo-file-system/legacy');
    return await FS.readAsStringAsync(uri, { encoding: 'base64' as any });
  } catch {
    const FS = await import('expo-file-system');
    // @ts-ignore — legacy API still exposed on some SDKs
    return await FS.readAsStringAsync(uri, { encoding: 'base64' });
  }
}
