
echo "sending to tomcat -----------------START---"
#scp target/*.war pi@192.168.178.41:/var/lib/tomcat8/webapps/
#cd target
#	for f in *.war ; do echo $f; mv -v "$f" "PRE_$f" ; done
#cd ..
cp target/*.war /root/warcache/
cp -v target/*.war /var/lib/tomcat8/webapps/
echo "sending to tomcat -----------------END-----"
