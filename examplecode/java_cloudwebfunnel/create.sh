
echo "----- START ----"

START=$(date +%s.%N)

if [ "$1" ]; then
  echo "TargetPlatform: $1"
else
  echo "E1: no known target given in create.sh Platform(GOOGLE) project(qr,seo,cc,pifme)"
  exit 1
fi


if [ "$2" ]; then
  echo "Projecttarget: $2"
else
  echo "E2: no known target given in create.sh Platform(GOOGLE) project(qr,seo,cc,pifme)"
  exit 1
fi

TARGET="$1"
PROJECTTARGET="$2"

if [ "$PROJECTTARGET" != "qr" ] && [ "$PROJECTTARGET" != "seo" ] &&  [ "$PROJECTTARGET" != "cc" ] &&  [ "$PROJECTTARGET" != "pifme" ] &&  [ "$PROJECTTARGET" != "seocms" ]
then
    echo "Projecttarget '$PROJECTTARGET' is unknown, --STOP--\n"
    exit
fi



dir=$PWD
projectname="$(basename $dir)"  # Returns just "to"


echo ""
echo "<------------------------------------------------------------>"
echo "<-------- BUILD  $projectname for $TARGET"
echo "<-------- in  $dir"
echo "<------------------------------------------------------------>"
echo ""
echo "Info......"
mvn -version

echo "clean......"
#mvn -q clean:clean 

END=$(date +%s.%N)
DIFF=$(echo "$END - $START" | bc)
echo "took 1 $DIFF sec!"

rm -rf $dir/docs/*
#rm -rf $dir/extjars/*
#rm -rf $dir/target/*
rm -rf $dir/target/*.war


#increase build counter
#typeset -i 

#not here on that server!
COUNTER=$(cat $dir/src/main/resources/build.count)
#echo "WERT ist: ${COUNTER}"
#COUNTER=$((COUNTER+1))
#echo "WERT ist jetzt: ${COUNTER}"
#echo $COUNTER > $dir/src/main/resources/build.count

PROJECTNAME=$(echo $dir | perl -F\/ -wane 'print $F[-1]')
HOSTNAME=$(echo `hostname`)
OSVERSION=$(echo `mvn -version | grep "OS name"`)

#write it to a properties file
NOW=$(date +'%m/%d/%YT%H:%M:%S')
echo "mvnbuild.version=${COUNTER}\nmvnbuild.date=${NOW}\nmvnbuild.name=${PROJECTNAME}\nmvnbuild.host=${HOSTNAME}\nmvnbuild.user=${USER}\nmvnbuild.osversion=${OSVERSION}" > $dir/src/main/resources/build.properties


END=$(date +%s.%N)
DIFF=$(echo "$END - $START" | bc)
echo "took 2 $DIFF sec!"

echo "git it......"
git add -A
git commit -m "autocommit changes on ${NOW} for Version ${COUNTER}" -a
#git gc --aggressive

#mvn site
#mvn compile package

#hetzner vm:
#xmvn -DskipTests=true -Dmaven.test.skip=true -DgenerateReports=false  site
#xmvn -DskipTests=true -Dmaven.test.skip=true -DgenerateReports=false  compile package

END=$(date +%s.%N)
DIFF=$(echo "$END - $START" | bc)
echo "took 2b $DIFF sec!"
echo "site......"

mymvn() {
mvn -T 4 -q $1  -DskipTests=true -DgenerateReports=false  -Dmaven.javadoc.skip=true 
# -T 4 use 4 cores
# -q dont show infos = quiet
}

#generates site docu
#mymvn site 

END=$(date +%s.%N)
DIFF=$(echo "$END - $START" | bc)
echo "took 3 $DIFF sec!"

rc=$?
if [ $rc -ne 0 ] ; then
  echo Could not perform mvn build, exit code [$rc]; 
  echo ""
  exit $rc
fi


echo "compile......"
mymvn compile 

#copy settings and templates
echo "copy settings......"
cp -r ../cloudconfig/$PROJECTTARGET/* $dir/target/classes/.
cp -r ../cloudtemplateresources/$PROJECTTARGET/templates/* $dir/target/classes/templates/.

END=$(date +%s.%N)
DIFF=$(echo "$END - $START" | bc)
echo "took 4 $DIFF sec!"

echo "package......"
mymvn package  

END=$(date +%s.%N)
DIFF=$(echo "$END - $START" | bc)
echo "took 4b $DIFF sec!"
#-Dmaven.test.skip=true

rm -rf /var/www/home/javadoc/$projectname
rm -rf /var/www/home/pmd/$projectname

DIRECTORY="/var/www/home/javadoc/$projectname/$TARGET"
if [ ! -d "$DIRECTORY" ]; then
mkdir -p "$DIRECTORY"
fi 

DIRECTORY="/var/www/home/pmd/$projectname/$TARGET"
if [ ! -d "$DIRECTORY" ]; then
mkdir -p "$DIRECTORY"
fi 

DIRECTORY="/var/www/home/javaoutput/$TARGET"
if [ ! -d "$DIRECTORY" ]; then
mkdir -p "$DIRECTORY"
fi 

if [ "$projectname"  = "cloudlib"   ]; then
  mvn install:install-file -Dfile=./target/cloudlib.jar -DgroupId=de.ovmedia.libs -DartifactId=cloudlib -Dversion=1 -Dpackaging=jar
fi

END=$(date +%s.%N)
DIFF=$(echo "$END - $START" | bc)
echo "took 5 $DIFF sec!"

echo "---- copy stuff ----"

cp -r docs/* "/var/www/home/javadoc/$PROJECTTARGET/$projectname/$TARGET"
cp -r target/site/* "/var/www/home/pmd/$PROJECTTARGET/$projectname/$TARGET"
cd target
	for f in *.war ; do echo $f; mv -v "$f" "$PROJECTTARGET$f" ; done
cd ..
cp -v target/*.war "/var/www/home/javaoutput/$TARGET"
cp -v target/*.war "/home/tomcat9prodcms/webapps/"

date
END=$(date +%s.%N)
DIFF=$(echo "$END - $START" | bc)
echo "took 6 $DIFF sec!"

echo "copy to server start"
#scp -T target/*.war 116.203.28.44:/var/lib/tomcat8/webapps/
echo "copy to server done"

rc=$?
if [ $rc -ne 0 ] ; then
  echo Could not perform scp [$rc]; 
  echo ""
  exit $rc
else
  echo "copy successfull"
fi

echo "finished at $(date)"

END=$(date +%s.%N)
DIFF=$(echo "$END - $START" | bc)

echo "took $DIFF sec!"
echo ""

exit

ERRCOUNTER=0
if [ -f "${dir}/target/*.jar" ]; then
ERRCOUNTER=$((ERRCOUNTER+1))
echo "jar found"
fi
if [ -f $dir/target/*.war ]; then
ERRCOUNTER=$((ERRCOUNTER+1))
echo "war found"
fi
if [ "$ERRCOUNTER" -eq "0" ];then
#	echo "X!!!!!!!!ERROR!!!!!!!!!!X"
#	echo "    WAR for ${dir} not found!      "
#	echo "X!!!!!!!!ERROR!!!!!!!!!!X"
#	echo "i wait now that you can stop me"
	exit 0
else    
	echo "BUILD Success"
	exit 1
fi