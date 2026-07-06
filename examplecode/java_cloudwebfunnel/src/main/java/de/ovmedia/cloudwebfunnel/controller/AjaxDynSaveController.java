package main.java.de.ovmedia.cloudwebfunnel.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import de.ovmedia.lib.AController;
import de.ovmedia.lib.Controller;
import de.ovmedia.lib.Helper;
import de.ovmedia.model.Ajaxresult;
import de.ovmedia.model.Customer;
import de.ovmedia.services.JsonToCustomer;
import de.ovmedia.services.JsonToEventtracker;
import de.ovmedia.transport.Customerlist;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.PrintWriter;
import org.apache.log4j.Logger;
import org.json.simple.JSONObject;
import org.json.simple.parser.JSONParser;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.MalformedURLException;
import java.net.URL;
import java.util.List;

public class AjaxDynSaveController extends AController {
  public void doAll(HttpServletRequest request, HttpServletResponse response, String Method)
      throws ServletException, IOException {
    try {
      Controller c = new LocalController();
      c.doAll(request, response);
    } catch (Exception e) {
      e.printStackTrace();
    }
  }

  public class LocalController extends Controller {

    private Logger log = Logger.getLogger("anything");

    public void doAll(HttpServletRequest request, HttpServletResponse response) throws ServletException, IOException {
      try {

        super.doAll(request, response);
        StringBuffer jb = new StringBuffer();

        String line = null;

        PrintWriter out = response.getWriter();

        try {
          BufferedReader reader = request.getReader();
          while ((line = reader.readLine()) != null)
            jb.append(line);
        } catch (Exception e) {
          e.printStackTrace();
          returnresult(out, 2, "REX");
        }
        String str = jb.toString();

        String regJson = str;

        response.setContentType("application/json");

        JSONObject injson = parseJson(str);

        this.log.info("datain:" + str);

        // email = (String) injson.get("email");

        URL url = new URL("https://hook.eu1.make.com/75ad0wlye4jk1bvhsuyfa88vu9s3b7qd");
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setDoOutput(true);
        conn.setRequestMethod("POST");
        conn.setRequestProperty("Content-Type", "application/json");

        OutputStream os = conn.getOutputStream();
        os.write(regJson.getBytes());
        os.flush();

        BufferedReader br = new BufferedReader(new InputStreamReader((conn.getInputStream())));

        String output;
        String input = "";
        // System.out.println("Output from Server .... \n");
        while ((output = br.readLine()) != null) {
          input = input + output;
          // System.out.println(output);
        }

        log.info("result:" + input);

        conn.disconnect();

        returnresult(out, 1, "OK");

      } catch (Exception e) {
        e.printStackTrace();
        this.log.info(Helper.exceptionToString(e));
      }
    }

    public void returnresult(PrintWriter out, int code, String message) {

      Ajaxresult regresult = new Ajaxresult();
      ObjectMapper objectMapper = new ObjectMapper();

      try {
        regresult.setResultcode(code);
        regresult.setResulttxt(message);
        String json = objectMapper.writeValueAsString(regresult);
        out.println(json);
        this.log.info("returnresult1 error:" + code + " " + message);
      } catch (Exception e) {
        this.log.info("returnresult2 error:" + code + " " + message);
      }

    }

    public JSONObject parseJson(String outputstr) {
      JSONObject json2 = null;
      try {
        System.out.println("now try to parse Begin:" + outputstr);
        JSONParser parser = new JSONParser();
        json2 = (JSONObject) parser.parse(outputstr);
      } catch (Exception e) {
        e.printStackTrace();
        this.log.info(Helper.exceptionToString(e));
      }
      return json2;
    }

    public boolean testSeriousness(String text) {
      return !text.toUpperCase().contains("FUNNY");
    }
  }
}
