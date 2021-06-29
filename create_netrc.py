from __future__ import print_function
import os
import netrc
import getpass

try:
    input = raw_input  # Check for python 2
except NameError:
    pass

NASAHOST = "urs.earthdata.nasa.gov"
NETRC_FILE = "~/.netrc"


class Netrc(netrc.netrc):
    """Handles saving of .netrc file, fixes bug in stdlib older versions
    https://bugs.python.org/issue30806
    Uses ideas from tinynetrc
    """

    def format(self):
        """Dump the class data in the format of a .netrc file.
        Fixes issue of including single quotes for username and password"""
        rep = ""
        for host in self.hosts.keys():
            attrs = self.hosts[host]
            rep += "machine {host}\n\tlogin {attrs[0]}\n".format(host=host, attrs=attrs)
            if attrs[1]:
                rep += "\taccount {attrs[1]}\n".format(attrs=attrs)
            rep += "\tpassword {attrs[2]}\n".format(attrs=attrs)
        for macro in self.macros.keys():
            rep += "macdef {macro}\n".format(macro=macro)
            for line in self.macros[macro]:
                rep += line
            rep += "\n"

        return rep

    def __repr__(self):
        return self.format()

    def __str__(self):
        return repr(self)


class ASFCredentials(object):
    def has_nasa_netrc(self):
        try:
            n = self.get_netrc_file()
            # Check account exists, as well is having username and password
            return (
                NASAHOST in n.hosts
                and n.authenticators(NASAHOST)[0]
                and n.authenticators(NASAHOST)[2]
            )
        except (OSError, IOError):
            return False

    def handle_credentials(self):
        """Prompt user for NASA username/password, store as attribute or .netrc
        If the user wants to save as .netrc, add to existing, or create new ~/.netrc
        """
        username, password, save_creds = self._get_username_pass()

        if save_creds:
            try:
                # If they have a netrc existing, add to it
                n = self.get_netrc_file()
                n.hosts[NASAHOST] = (username, None, password)
                outstring = str(n)
            except (OSError, IOError):
                # Otherwise, make a fresh one to save
                outstring = self._nasa_netrc_entry(username, password)

            with open(self._user_netrc_file, "w") as f:
                f.write(outstring)
            # access permissions must restrict access to only the owner
            # Permission: 0o600 == 384
            os.chmod(self._user_netrc_file, 384)
            return None, None
        else:
            # Save these as attritubes for the NASA url request
            return username, password

    @staticmethod
    def _get_username_pass():
        """If netrc is not set up, get command line username and password"""
        print("====================================================================")
        print("Please enter NASA Earthdata credentials to download ASF hosted data.")
        print("For new user signups, see https://urs.earthdata.nasa.gov/users/new .")
        print("===========================================")
        username = input("Username: ")
        password = getpass.getpass(prompt="Password (will not be displayed): ")
        save_to_netrc = input(
            "Would you like to save these to ~/.netrc (machine={}) for future use (y/n)?  ".format(
                NASAHOST
            )
        )
        return username, password, save_to_netrc.lower().startswith("y")

    @property
    def _user_netrc_file(self):
        return os.path.expanduser(NETRC_FILE)

    def get_netrc_file(self):
        return Netrc(self._user_netrc_file)

    @staticmethod
    def _nasa_netrc_entry(username, password):
        """Create a string for a NASA urs account in .netrc format"""
        outstring = "machine {}\n".format(NASAHOST)
        outstring += "\tlogin {}\n".format(username)
        outstring += "\tpassword {}\n".format(password)
        return outstring
