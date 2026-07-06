
echo "----- START ----"

START=$(date +%s.%N)

if [ "$1" ]; then
  echo "TargetPlatform: $1"
else
  echo "E1: no known target given in create.sh Platform(GOOGLE) project(qr,seo,cc)"
  exit 1
fi


if [ "$2" ]; then
  echo "project: $2"
else
  echo "E2: no known target given in create.sh Platform(GOOGLE) project(qr,seo,cc)"
  exit 1
fi

TARGET="$1"
PROJECTTARGET="$2"

dir=$PWD
projectname="$(basename $dir)"  # Returns just "to"


echo ""
echo "<------------------------------------------------------------>"
echo "<-------- BUILD  $projectname for $TARGET ($PROJECTTARGET)"
echo "<-------- in  $dir"
echo "<------------------------------------------------------------>"
echo ""
echo "Info......"


#for f in *.war ; do echo $f; mv -v "$f" "$PROJECTTARGET$f" ; done

#scp -T ../cloudtemplateresources/seo/templates/* 116.203.28.44:/var/lib/tomcat8/webapps/$PROJECTTARGET$projectname/WEB-INF/classes/templates
#scp -T src/main/resources/templates/* 116.203.28.44:/var/lib/tomcat8/webapps/$PROJECTTARGET$projectname/WEB-INF/classes/templates

cp -r ../cloudtemplateresources/seo/templates/* /var/lib/tomcat9/webapps/$PROJECTTARGET$projectname/WEB-INF/classes/templates
cp -r  src/main/resources/templates/* /var/lib/tomcat9/webapps/$PROJECTTARGET$projectname/WEB-INF/classes/templates
echo "DONE"
