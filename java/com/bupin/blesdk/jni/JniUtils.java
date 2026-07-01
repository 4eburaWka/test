package com.bupin.blesdk.jni;

/**
 * JNI stubs for libbluetoothhelper.so (same as TableCard APK).
 * Implementation lives in the native library extracted from APK.
 */
public final class JniUtils {
    static {
        System.loadLibrary("bluetoothhelper");
    }

    private JniUtils() {
    }

    public static native byte[] BleCallBack(byte[] data);

    public static native byte[] CreateImage(int[] pixelsA, int[] pixelsB, int lcdType, int screenCode);

    public static native String ScanCallBack(byte[] scanRecord);

    public static native byte[] SetID(int id, short groupId);

    public static native byte[] SetIDCallBack(byte[] data);
}
