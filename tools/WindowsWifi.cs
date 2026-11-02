using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
using System.Xml;

namespace Bricq {
    public class WifiConnection {
        public Guid InterfaceId;
        public string Profile;
        public byte[] Ssid;
        public string Name { get { return Encoding.UTF8.GetString(Ssid); } }
    }
    public static class WindowsWifi {
        [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
        private struct InterfaceInfo {
            public Guid Id;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst=256)] public string Description;
            public int State;
        }
        [DllImport("wlanapi.dll")] private static extern uint WlanOpenHandle(uint v, IntPtr r, out uint negotiated, out IntPtr h);
        [DllImport("wlanapi.dll")] private static extern uint WlanCloseHandle(IntPtr h, IntPtr r);
        [DllImport("wlanapi.dll")] private static extern uint WlanEnumInterfaces(IntPtr h, IntPtr r, out IntPtr list);
        [DllImport("wlanapi.dll")] private static extern void WlanFreeMemory(IntPtr p);
        [DllImport("wlanapi.dll")] private static extern uint WlanQueryInterface(IntPtr h, ref Guid id, int opcode, IntPtr r, out uint size, out IntPtr data, out int type);
        [DllImport("wlanapi.dll", CharSet=CharSet.Unicode)]
        private static extern uint WlanGetProfile(IntPtr h, ref Guid id, string name, IntPtr r, out IntPtr xml, ref uint flags, out uint access);

        private static void Check(uint code) {
            if (code != 0) throw new Win32Exception((int)code);
        }
        public static WifiConnection Current() {
            IntPtr h = IntPtr.Zero, list = IntPtr.Zero;
            uint version;
            try {
                Check(WlanOpenHandle(2, IntPtr.Zero, out version, out h));
                Check(WlanEnumInterfaces(h, IntPtr.Zero, out list));
                int count = Marshal.ReadInt32(list);
                WifiConnection current = null;
                for (int i=0; i<count; i++) {
                    var info = (InterfaceInfo)Marshal.PtrToStructure(IntPtr.Add(list, 8+i*Marshal.SizeOf(typeof(InterfaceInfo))), typeof(InterfaceInfo));
                    if (info.State != 1) continue;
                    if (current != null) throw new InvalidOperationException("More than one Wi-Fi adapter is connected.");
                    IntPtr data = IntPtr.Zero;
                    uint size; int type;
                    try {
                        Check(WlanQueryInterface(h, ref info.Id, 7, IntPtr.Zero, out size, out data, out type));
                        // WLAN_CONNECTION_ATTRIBUTES: two enums, WCHAR profile[256], DOT11_SSID.
                        if (size < 556) throw new InvalidOperationException("Unexpected WLAN connection data.");
                        int length = Marshal.ReadInt32(data, 520);
                        if (length < 1 || length > 32) throw new InvalidOperationException("Invalid SSID length.");
                        byte[] ssid = new byte[length];
                        Marshal.Copy(IntPtr.Add(data, 524), ssid, 0, length);
                        current = new WifiConnection { InterfaceId=info.Id, Ssid=ssid,
                            Profile=Marshal.PtrToStringUni(IntPtr.Add(data, 8), 256).TrimEnd('\0') };
                    } finally { if (data != IntPtr.Zero) WlanFreeMemory(data); }
                }
                if (current == null) throw new InvalidOperationException("Connect this laptop to Wi-Fi first.");
                return current;
            } finally {
                if (list != IntPtr.Zero) WlanFreeMemory(list);
                if (h != IntPtr.Zero) WlanCloseHandle(h, IntPtr.Zero);
            }
        }
        // Call only after the user confirms sharing the current network with BRICQ.
        // Returns a WPA PSK. Never print or serialize this except to encrypted SSH stdin.
        public static string ReadPsk(WifiConnection connection) {
            IntPtr h=IntPtr.Zero, xml=IntPtr.Zero;
            uint version, flags=4, access;
            try {
                Check(WlanOpenHandle(2, IntPtr.Zero, out version, out h));
                Guid id=connection.InterfaceId;
                Check(WlanGetProfile(h, ref id, connection.Profile, IntPtr.Zero, out xml, ref flags, out access));
                var doc=new XmlDocument();
                doc.XmlResolver=null;
                doc.LoadXml(Marshal.PtrToStringUni(xml));
                var ns=new XmlNamespaceManager(doc.NameTable);
                ns.AddNamespace("w", doc.DocumentElement.NamespaceURI);
                var auth=doc.SelectSingleNode("/w:WLANProfile/w:MSM/w:security/w:authEncryption/w:authentication", ns);
                if (auth == null || (auth.InnerText != "WPA2PSK" && auth.InnerText != "WPAPSK"))
                    throw new InvalidOperationException("Automatic sharing currently supports WPA/WPA2 Personal only.");
                var key=doc.SelectSingleNode("/w:WLANProfile/w:MSM/w:security/w:sharedKey", ns);
                if (key == null) throw new InvalidOperationException("No saved Wi-Fi password is available.");
                var protection=key.SelectSingleNode("w:protected", ns);
                var material=key.SelectSingleNode("w:keyMaterial", ns);
                if (protection == null || protection.InnerText != "false" || material == null)
                    throw new InvalidOperationException("Windows denied saved-password access. Try an Administrator PowerShell, or use manual Wi-Fi setup. No permissions were changed.");
                string password=material.InnerText;
                var keyType=key.SelectSingleNode("w:keyType", ns);
                if (keyType != null && keyType.InnerText == "networkKey") {
                    if (!System.Text.RegularExpressions.Regex.IsMatch(password, @"\A[0-9a-fA-F]{64}\z"))
                        throw new InvalidOperationException("Unsupported saved Wi-Fi key format.");
                    return password.ToLowerInvariant();
                }
                // WPA/WPA2 requires PBKDF2-SHA1 with 4096 iterations.
                // Keep support for Windows PowerShell 5.1 and PowerShell 7.
                using (var derive=(System.Security.Cryptography.Rfc2898DeriveBytes)Activator.CreateInstance(
                    typeof(System.Security.Cryptography.Rfc2898DeriveBytes),
                    new object[] { password, connection.Ssid, 4096 })) {
                    byte[] psk=derive.GetBytes(32);
                    return BitConverter.ToString(psk).Replace("-", "").ToLowerInvariant();
                }
            } finally {
                if (xml != IntPtr.Zero) {
                    // Clear the unmanaged XML buffer, which can contain a plaintext password.
                    int length=0;
                    while (Marshal.ReadInt16(xml, length*2) != 0) length++;
                    for (int i=0; i<length*2; i++) Marshal.WriteByte(xml, i, 0);
                    WlanFreeMemory(xml);
                }
                if (h != IntPtr.Zero) WlanCloseHandle(h, IntPtr.Zero);
            }
        }
    }
}
