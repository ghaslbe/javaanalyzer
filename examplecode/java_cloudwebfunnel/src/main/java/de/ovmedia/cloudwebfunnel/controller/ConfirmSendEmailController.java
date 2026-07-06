package main.java.de.ovmedia.cloudwebfunnel.controller;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.*;
import java.text.DecimalFormat;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;
import java.io.File;
import java.util.Map;
import java.util.Properties;
import java.util.List;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.Locale;

import java.io.PrintWriter;
import java.io.PrintWriter;
import java.util.HashMap;
import java.util.Map;
import java.lang.Enum;
import java.util.Enumeration;
import java.net.InetAddress;

import de.ovmedia.lib.*;
import de.ovmedia.model.*;
import de.ovmedia.util.*;
import de.ovmedia.connector.*;
import de.ovmedia.services.*;
import de.ovmedia.services.JsonToCustomer;
import de.ovmedia.services.*;
import de.ovmedia.transport.Customerlist;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.*;
import jakarta.servlet.*;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import de.ovmedia.lib.*;
import de.ovmedia.model.*;
import de.ovmedia.util.*;
import de.ovmedia.connector.*;
import de.ovmedia.services.*;
//import de.ovmedia.pflege.*;
import org.json.simple.JSONObject;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.ZoneOffset;

import de.ovmedia.services.JsonToCloudDataStore;

import org.apache.log4j.Logger;
import org.json.simple.JSONObject;
import org.json.simple.parser.JSONParser;

@SuppressWarnings("serial")
public class ConfirmSendEmailController extends AController {


	public void doAll(HttpServletRequest request, HttpServletResponse response, String Method) throws ServletException, IOException {

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

	public void doAll(HttpServletRequest request, HttpServletResponse response) throws ServletException, IOException {

		//System.out.println("login: CloudinternalSTARTController started----------------------");
		try {

			super.doAll(request, response);

			// helper.log("hello");
			Map<String, Object> params = new HashMap<String, Object>();


			String id = request.getParameter("id");
			params.put("inputid", id);	

			log.info("confirm SendEmail");

		try{

		
		} catch (Exception e) {
			e.printStackTrace();
			log.info("ups... Exception happened");
						
		}
			//now update customer here

			super.display("pflege", "/templates/confirmsendemail.twig", params);

			
		} catch (Exception e) {
			// TODO Auto-generated catch block
			e.printStackTrace();

		}
		//System.out.println("login: CloudinternalSTARTController ended----------------------");

	}

	public boolean testSeriousness(String text) {
		//System.out.println("test got:" + text);
		return !text.toUpperCase().contains("FUNNY");
	}

}
}
