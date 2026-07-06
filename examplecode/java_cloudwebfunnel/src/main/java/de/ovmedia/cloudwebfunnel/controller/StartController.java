package main.java.de.ovmedia.cloudwebfunnel.controller;

import de.ovmedia.lib.AController;
import de.ovmedia.lib.Controller;
import de.ovmedia.lib.Helper;
import de.ovmedia.model.Customer;
import de.ovmedia.model.Funnel;
import de.ovmedia.model.FunnelQuestions;
import de.ovmedia.services.JsonFunnelNow;
import de.ovmedia.services.JsonToCustomer;
import de.ovmedia.services.JsonToEventtracker;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class StartController extends AController {
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
    public void doAll(HttpServletRequest request, HttpServletResponse response) throws ServletException, IOException {
      try {

        super.doAll(request, response);

        Map<String, Object> params = new HashMap<>();

        String funnelid = request.getParameter("id");
        params.put("inputid", funnelid);
        params.put("funnelid", funnelid);

        JsonFunnelNow djcn = new JsonFunnelNow();
        List<Funnel> codelist = djcn.jsonGetQrcode("", funnelid);

        params.put("codelist", codelist);
        Funnel fl1 = codelist.get(0);

        // if (fl1.get..()) = Questions
        List<FunnelQuestions> funnelquestions = djcn.jsonGetFunnelQuestions("", funnelid);
        params.put("funnelquestions", funnelquestions);

        String customerid = "";
        JsonToEventtracker t2et = new JsonToEventtracker();

        if (fl1.getLandingpageType() == null) {
          fl1.setLandingpageType("0");
        }

        if (fl1.getLandingpageType().equals("1")) {
          log.info(funnelid + ": this is a formfunnel");

          String fl1owner = fl1.getUserId();
          String doi = fl1.getDoi();
          String followfunnelid = fl1.getFollowfunnelId();
          String fnlEmail4seriesId = fl1.getEmail4seriesId();
          String fnlEmail4pdfId = fl1.getEmail4pdfId();
          this.log.info("got funnel data");

          Customer cu = new Customer();
          cu.setCustomerId("");
          cu.setUserId(fl1owner);
          cu.setFirstname("FUNNEL");
          cu.setLastname("FUNNEL");
          cu.setEmail("");
          cu.setVerified("0");
          cu.setDoiNeeded(doi);
          cu.setCreationfunnelid(funnelid);
          cu.setFollowfunnelid(followfunnelid);
          cu.setFollowEmail4seriesId(fnlEmail4seriesId);
          cu.setFollowEmail4pdfId(fnlEmail4pdfId);
          this.log.info("customer created in mem, no send");

          String cookieName = "uu";
          String cookieValue = "";

          if (this.extradata.get("input_cookie_" + cookieName) != null) {
            customerid = (String) this.extradata.get("input_cookie_" + cookieName);
            customerid = customerid.replaceAll("[\\$'\"; ]", "_");
            this.log.info("found Customerid " + customerid + " from cookie");
          }

          String newcustomerid = request.getParameter("newcustomerid");
          if (newcustomerid != null && !newcustomerid.equals("")) {
            customerid = "";
            this.log.info("delete Customerid to get a new one");
          }

          if (customerid == null || customerid.equals("")) {
            JsonToCustomer dj2 = new JsonToCustomer();
            customerid = dj2.jsonAddCustomer(fl1owner, cu);
            setCookie(cookieName, customerid, 365);
            this.log.info("create new Cookie and Customerid");
            t2et.storeFunnelEvent(funnelid, "FUNNEL.NEWCUSTOMER", "" + customerid, "");
            t2et.storeCustomerEvent(customerid, "CUSTOMER.CREATED", "funnel:" + funnelid, "");
          }

          this.log.info("using customer:'" + customerid + "'");
          params.put("cid", customerid);

          /*
           * Enumeration<String> headerNames = request.getHeaderNames();
           * if (headerNames != null)
           * while (headerNames.hasMoreElements()) {
           * String headerName = headerNames.nextElement();
           * String headerValue = request.getHeader(headerName);
           * this.log.info("Header: " + headerName + "=" + headerValue);
           * }
           */

        }
        if (fl1.getLandingpageType().equals("2")) {
          log.info(funnelid + ": this is a linkfunnel");

          String cid = request.getParameter("cid");
          if ((cid != null) && (!cid.equals(""))) {
            params.put("cid", cid);
            t2et.storeCustomerEvent(cid, "CUSTOMER.SHOW-DOWNLOAD", "funnel:" + funnelid, "");
          }
        }

        // ------------------------------------------------------------

        String utm_source = request.getParameter("utm_source");
        if (utm_source != null) {
          utm_source = utm_source.replaceAll("[\\$'\"]", "_");
          params.put("utm_source", utm_source);
        }
        String utm_campaign = request.getParameter("utm_campaign");
        if (utm_campaign != null) {
          utm_campaign = utm_campaign.replaceAll("[\\$'\"]", "_");
          params.put("utm_campaign", utm_campaign);
        }
        String utm_medium = request.getParameter("utm_medium");
        if (utm_medium != null) {
          utm_medium = utm_medium.replaceAll("[\\$'\"]", "_");
          params.put("utm_medium", utm_medium);
        }
        String utm_content = request.getParameter("utm_content");
        if (utm_content != null) {
          utm_content = utm_content.replaceAll("[\\$'\"]", "_");
          params.put("utm_content", utm_content);
        }

        // ------------------------------------------------------------

        if ((customerid != null) && (!customerid.equals(""))) {

          if (utm_source != null && !utm_source.equals(""))
            t2et.storeCustomerEvent(customerid, "CUSTOMER.INFO", "utm_source:" + utm_source, "");
          if (utm_campaign != null && !utm_campaign.equals(""))
            t2et.storeCustomerEvent(customerid, "CUSTOMER.INFO", "utm_campaign:" + utm_campaign, "");
          if (utm_medium != null && !utm_medium.equals(""))
            t2et.storeCustomerEvent(customerid, "CUSTOMER.INFO", "utm_medium:" + utm_medium, "");
          if (utm_content != null && !utm_content.equals(""))
            t2et.storeCustomerEvent(customerid, "CUSTOMER.INFO", "utm_source:" + utm_content, "");
          if (this.browserName != null && !this.browserName.equals(""))
            try {
              this.browserName = request.getHeader("user-agent");
            } catch (Exception exception) {
            }
          if (this.browserName != null && !this.browserName.equals("")) {
            String xbrowserName = this.browserName.replaceAll("[\\$'\"]", "_");
            t2et.storeCustomerEvent(customerid, "CUSTOMER.INFO", "browserName:" + xbrowserName, "");
          } else {
            this.log.info("User-Agent not given");
          }

        }

        display("pflege", "/templates/funnel.twig", params);
      } catch (Exception e) {
        e.printStackTrace();
        this.log.info(Helper.exceptionToString(e));
      }
    }

    public boolean testSeriousness(String text) {
      return !text.toUpperCase().contains("FUNNY");
    }
  }
}
