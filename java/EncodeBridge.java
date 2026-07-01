package com.bupin.pm970;

import com.bupin.blesdk.jni.JniUtils;

import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/**
 * CLI bridge: Python -> JniUtils (libbluetoothhelper.so).
 *
 * stdin : binary payload (see readBytes / readPixels)
 * stdout: OK\n{hex}\n  or  OK_TEXT\n{text}\n  or  ERR\n{message}\n
 */
public final class EncodeBridge {

    private EncodeBridge() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            fail("command required: create_image | ble_callback | scan_callback");
        }

        String command = args[0];
        DataInputStream in = new DataInputStream(System.in);

        switch (command) {
            case "create_image":
                ok(hex(createImage(in)));
                break;
            case "ble_callback":
                ok(hex(JniUtils.BleCallBack(readBytes(in))));
                break;
            case "scan_callback":
                okText(JniUtils.ScanCallBack(readBytes(in)));
                break;
            default:
                fail("unknown command: " + command);
        }
    }

    private static byte[] createImage(DataInputStream in) throws IOException {
        int lcdType = in.readInt();
        int screenCode = in.readInt();
        int[] pixelsA = readPixels(in);
        int[] pixelsB = readPixels(in);
        return JniUtils.CreateImage(pixelsA, pixelsB, lcdType, screenCode);
    }

    private static int[] readPixels(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0) {
            throw new IOException("invalid pixel array length: " + length);
        }
        int[] values = new int[length];
        for (int i = 0; i < length; i++) {
            values[i] = in.readInt();
        }
        return values;
    }

    private static byte[] readBytes(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0) {
            throw new IOException("invalid byte array length: " + length);
        }
        byte[] data = new byte[length];
        in.readFully(data);
        return data;
    }

    private static String hex(byte[] data) {
        StringBuilder builder = new StringBuilder(data.length * 2);
        for (byte value : data) {
            builder.append(String.format("%02x", value & 0xFF));
        }
        return builder.toString();
    }

    private static void ok(String dataHex) {
        System.out.println("OK");
        System.out.println(dataHex);
    }

    private static void okText(String text) {
        System.out.println("OK_TEXT");
        System.out.println(text);
    }

    private static void fail(String message) {
        System.out.println("ERR");
        System.out.println(message);
        System.exit(1);
    }
}
