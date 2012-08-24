Renkisrv is server-side client for Services database.

Renkisrv is used to create, modify and delete configs based on database 
changes.

Installation:

virtualenv env
. env/bin/activate
pip install -r requirements.txt
cp config.py.sample config.py 
$EDITOR config.py
./renkisrv

# Getting started with user_ports
Currently user_ports is dummy script which adds and removes lines
from /etc/ports.conf file.

# Getting started with apache
Configure apache settings to config.py file.
Create required dirs if not already exists.
Add "include your_apache_vhosts_dir/*.conf" to apache2.conf

# Getting started with bind
Add "acl "slaves"" to named.conf.local
Eg. "acl "slaves" { myslave; myotherslave; };"

Create dnssec key for dynamic updates
dnssec-keygen -a HMAC-SHA512 -b 512 -n USER hostmaster_address.domain.dom
Copy secret from Khostmaster_address.domain.dom.+whatever.key
Add line "key "renkisrv" {algorithm hmac-sha512; secret "paste secret here"};"

Copy secret from Khostmaster_address.domain.dom.+whatever.private and paste it
to config.py file.
Add key type (hmac-sha512) to config.py file

Licensed under MIT-license.

Copyright (c) 2012 Kapsi Internet-käyttäjät ry

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.