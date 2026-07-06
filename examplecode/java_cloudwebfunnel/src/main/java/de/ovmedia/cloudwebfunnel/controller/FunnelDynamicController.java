package main.java.de.ovmedia.cloudwebfunnel.controller;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URL;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import de.ovmedia.lib.AController;
import de.ovmedia.lib.Controller;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import de.ovmedia.lib.*;
import de.ovmedia.model.*;
import de.ovmedia.util.*;
import de.ovmedia.connector.*;
import de.ovmedia.services.*;
import org.json.simple.JSONObject;
import de.ovmedia.services.JsonToCustomer;

import org.apache.log4j.Logger;
import org.json.simple.JSONObject;
import org.json.simple.parser.JSONParser;

@SuppressWarnings("serial")
public class FunnelDynamicController extends AController {

	public void doAll(HttpServletRequest request, HttpServletResponse response, String Method)
			throws ServletException, IOException {

		try {
			Controller c = new LocalController();
			c.doAll(request, response);
		} catch (Exception e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		}

	}

	public class LocalController extends Controller {

		/**
		 * 
		 * THIS IS WEB ONLY (c) 2018 OM
		 * 
		 */

		private Logger log = Logger.getLogger("anything");

		public void doAll(HttpServletRequest request, HttpServletResponse response)
				throws ServletException, IOException {

			// System.out.println("login: CloudinternalSTARTController
			// started----------------------");
			try {

				super.doAll(request, response);

				// helper.log("hello");
				Map<String, Object> params = new HashMap<String, Object>();

				String funnelid = request.getParameter("f"); // funnel
				params.put("funnelid", funnelid);

				String pageid = request.getParameter("pid"); // page
				if ((pageid == null) || (pageid.equals(""))) {
					pageid = "start";
				}
				params.put("pageid", pageid);

				// this is for a temporary fake customerid... replace this with real customer
				// createion
				UUID uId = UUID.randomUUID();
				String userId = uId.toString();
				params.put("cid", userId);
				// this is for a temporary fake customerid... replace this with real customer
				// createion

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

				// READ JSON from inputfile

				String wikitext = "";
				JSONObject json2 = null;

				try {

					InputStream iStream = null;

					// Loading properties file from the path (relative path given here)
					// iStream = new
					// FileInputStream(this.getClass().getClassLoader().getResourceAsStream("test.txt"));

					URL resource = this.getClass().getResource("/templates/" + funnelid + ".json");
					log.info(resource);
					// URL resource = classLoader.getResource("resource.ext");
					File file = new File(resource.toURI());
					iStream = new FileInputStream(file);

					if (iStream != null) {

						StringBuilder content;

						content = new StringBuilder();

						BufferedReader br = new BufferedReader(new InputStreamReader(iStream));

						String line;

						while ((line = br.readLine()) != null) {
							// append string builder with line and with
							// '/n' or '/r' or EOF
							content.append(line + System.lineSeparator());
						}
						wikitext = content.toString();

						try {

							// System.out.println("now try to parse Begin:" + outputstr);

							JSONParser parser = new JSONParser(); // free json format
							json2 = (JSONObject) parser.parse(wikitext);

							params.put("jsondata", json2);

							// result = (String) json2.get("result");

						} catch (Exception e) {
							// TODO Auto-generated catch block
							e.printStackTrace();

						}

					} else {
						log.info("file is null");
					}

				} catch (Exception e) {
					e.printStackTrace();
					log.info("ups... Exception happened");

				}
				// now update customer here

				super.display("pflege", "/templates/dynamicfunnel_main.twig", params);

			} catch (Exception e) {
				// TODO Auto-generated catch block
				e.printStackTrace();

			}
			// System.out.println("login: CloudinternalSTARTController
			// ended----------------------");

		}

		public boolean testSeriousness(String text) {
			// System.out.println("test got:" + text);
			return !text.toUpperCase().contains("FUNNY");
		}

	}
}
