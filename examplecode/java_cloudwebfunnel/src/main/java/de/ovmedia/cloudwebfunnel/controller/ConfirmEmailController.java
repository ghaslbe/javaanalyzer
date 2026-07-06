package main.java.de.ovmedia.cloudwebfunnel.controller;

import de.ovmedia.lib.AController;
import de.ovmedia.lib.Controller;
import de.ovmedia.model.Customer;
import de.ovmedia.services.JsonToCustomer;
import de.ovmedia.services.JsonToEventtracker;
import de.ovmedia.transport.Customerlist;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

public class ConfirmEmailController extends AController {
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
        String id = request.getParameter("id");
        params.put("inputid", id);
        String[] idElements = id.split(";");
        String inuserid = idElements[1];
        params.put("inuserid", inuserid);
        try {
          if (inuserid != null) {
            this.log.info("customerid is given so try to get data");
            JsonToCustomer dj = new JsonToCustomer();
            Customerlist cl = dj.jsonSenderGetCustomer("", inuserid);

            if (cl != null) {
              params.put("customer", cl.getAll().get(0));
              Customer cu = cl.getAll().get(0);
              this.log.info("conform this customer:" + cu.getEmail());

              dj.jsonConfirmCustomerDOI(cu.getUserId(), cu.getCustomerId()); // this sends follow emails if defined
              this.log.info("send data back done");

              JsonToEventtracker t2et = new JsonToEventtracker();
              t2et.storeCustomerEvent(cu.getCustomerId(), "CUSTOMER.VERIFICATION-DONE", "", "");
              t2et.storeFunnelEvent(cu.getCreationfunnelid(), "STEP-VERIFICATION", "finished", "");

            } else {
              this.log.info("no response");
            }

          } else {
            this.log.info("customerid is not given!");
          }
        } catch (Exception e) {
          e.printStackTrace();
          this.log.info("ups... Exception happened");
        }
        display("pflege", "/templates/confirmemail.twig", params);
      } catch (Exception e) {
        e.printStackTrace();
      }
    }

    public boolean testSeriousness(String text) {
      return !text.toUpperCase().contains("FUNNY");
    }
  }
}
