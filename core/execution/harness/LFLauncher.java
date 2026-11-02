import java.io.BufferedInputStream;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.PrintStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

/**
 * Runs a student's main class with stdin echoed to stdout, so the captured
 * console reads like a real session ("Enter PIN: 1234") instead of hiding
 * the typed input. Hands out one line per read so echo order stays exact.
 */
public class LFLauncher {
    static final class EchoIn extends InputStream {
        private final InputStream in;
        private final PrintStream out;

        EchoIn(InputStream in, PrintStream out) {
            this.in = in;
            this.out = out;
        }

        @Override
        public int read() throws IOException {
            int c = in.read();
            if (c != -1) {
                out.write(c);
                out.flush();
            }
            return c;
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            if (len == 0) return 0;
            int n = 0;
            while (n < len) {
                int c = in.read();
                if (c == -1) break;
                b[off + n++] = (byte) c;
                if (c == '\n') break;
            }
            if (n == 0) return -1;
            out.write(b, off, n);
            out.flush();
            return n;
        }

        @Override
        public int available() {
            return 0;
        }
    }

    public static void main(String[] args) throws Exception {
        // Unbuffered: a prompt printed before a timeout kill still reaches the console.
        System.setOut(new PrintStream(new FileOutputStream(FileDescriptor.out), true, "UTF-8"));
        System.setErr(new PrintStream(new FileOutputStream(FileDescriptor.err), true, "UTF-8"));
        System.setIn(new EchoIn(new BufferedInputStream(System.in), System.out));
        Class<?> target = Class.forName(args[0]);
        Method main = target.getMethod("main", String[].class);
        main.setAccessible(true);
        try {
            main.invoke(null, (Object) new String[0]);
        } catch (InvocationTargetException e) {
            Throwable t = e.getCause();
            trim(t);
            System.out.flush();
            System.err.print("Exception in thread \"main\" ");
            t.printStackTrace();
            System.err.flush();
            System.exit(1);
        }
        System.out.flush();
        if (Boolean.getBoolean("lf.exit")) {
            System.exit(0); // Spring Boot: the runners are done; don't wait on the web server
        }
    }

    private static void trim(Throwable t) {
        while (t != null) {
            List<StackTraceElement> kept = new ArrayList<>();
            for (StackTraceElement el : t.getStackTrace()) {
                String cls = el.getClassName();
                if (cls.startsWith("jdk.internal.reflect") || cls.startsWith("java.lang.reflect")
                        || cls.equals("LFLauncher")) {
                    break;
                }
                kept.add(el);
            }
            t.setStackTrace(kept.toArray(new StackTraceElement[0]));
            t = t.getCause();
        }
    }
}
