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

public class AjaxSaveController extends AController {
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

        String email = "";
        String funnelUserId = "";
        String funnelName = "";
        String funnelHeadline = "";
        String funnelText = "";
        String funnelImage = "";
        String funnelLogo = "";
        String funnelWewe = "";
        int resultcode = 1;

        JSONObject injson = parseJson(str);

        this.log.info("datain:" + str);

        email = (String) injson.get("email");

        // not every event has an email!
        if ((email != null) && (!email.equals(""))) {

          email = email.toLowerCase();
          email = email.replace("\"", "");
          email = email.replace("\'", "");

          if (email.indexOf("@", 1) < 2) {
            log.info("Email ist keine Email:" + email);
            returnresult(out, 2, "NOEM");
            return;
          }
        }

        String mode = (String) injson.get("mode");
        String dataprotection = "";
        String wewe = "";
        String funnelid = "";
        String doi = "";
        String followfunnelid = "";
        String fnlEmail4seriesId = "";
        String fnlEmail4pdfId = "";

        dataprotection = (String) injson.get("dataprotection");
        wewe = (String) injson.get("wewe");
        funnelid = (String) injson.get("funnelid");
        doi = (String) injson.get("doi");
        followfunnelid = (String) injson.get("followfunnelid");
        fnlEmail4seriesId = (String) injson.get("fnlEmail4seriesId");
        fnlEmail4pdfId = (String) injson.get("fnlEmail4pdfId");

        String cookieName = "uu";
        String customerid = (String) injson.get("cid");

        if (this.extradata.get("input_cookie_" + cookieName) != null) {
          String cookieid = (String) this.extradata.get("input_cookie_" + cookieName);
          if (!cookieid.equals(customerid)) {
            this.log.warn("cookieid:" + cookieid + " passt nicht zu " + customerid);
            // returnresult(out,3,"COOWRN");
            // return;
          }
        }
        this.log.info("mode:" + mode);

        if (mode != null && mode.equals("track")) {
          this.log.info("track");
          String inkey = (String) injson.get("key");
          String invalue = (String) injson.get("value");
          if (inkey != null && !inkey.equals("")) {
            inkey = inkey.toUpperCase();
          }
          JsonToEventtracker t2et = new JsonToEventtracker();
          t2et.storeCustomerEvent(customerid, "CUSTOMER.EVENT", "" + inkey + ":" + invalue, "");

        } else if (mode != null && mode.equals("funnelstep")) {
          this.log.info("track");
          String inkey = (String) injson.get("key");
          String invalue = (String) injson.get("value");
          if (inkey != null && !inkey.equals(""))
            inkey = inkey.toUpperCase();
          JsonToEventtracker t2et = new JsonToEventtracker();
          t2et.storeFunnelEvent(funnelid, inkey, invalue, "");

        } else {
          this.log.info("save");
          if (customerid != null) {
            this.log.info("Update Customer:" + customerid);
            JsonToCustomer dj = new JsonToCustomer();
            Customerlist cl = dj.jsonSenderGetCustomer("", customerid);

            if (cl != null) {
              this.log.info("Found Customer:" + customerid);
              Customer cu = new Customer();

              try {
                cu = cl.getAll().get(0);
              } catch (Exception e) {
                returnresult(out, 8, "CUNF");
                return;
              }
              cu.setEmail(email);
              String result = dj.jsonAddCustomer(cu.getUserId(), cu);
              this.log.info("Save Customer:" + customerid + " res:" + result);
              result = dj.startCustomerVerification(cu.getUserId(), cu.getCustomerId());
              this.log.info("Verification for Customer :" + customerid + " started:" + result);
              JsonToEventtracker t2et = new JsonToEventtracker();
              t2et.storeCustomerEvent(customerid, "CUSTOMER.VERIFICATION-MAIL-STARTED", "", "");
              t2et.storeFunnelEvent(funnelid, "STEP-VERIFICATION", "started", "");
            }
          }
        }

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
