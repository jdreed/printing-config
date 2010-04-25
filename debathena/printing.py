"""Debathena printing configuration"""


import socket
import urllib

import cups
import hesiod


_loaded = False
CUPS_FRONTENDS = [
    'printers.mit.edu',
    'cluster-printer.mit.edu',
    'cups.mit.edu',
    ]
CUPS_BACKENDS = []
cupsd = None


SYSTEM_CUPS = 0
SYSTEM_LPRNG = 1


def _hesiod_lookup(hes_name, hes_type):
    """A wrapper with somewhat graceful error handling."""
    try:
        h = hesiod.Lookup(hes_name, hes_type)
        if len(h.results) > 0:
            return h.results
    except IOError:
        return []


def _setup():
    global _loaded
    if not _loaded:
        CUPS_BACKENDS = [s.lower() for s in
                         _hesiod_lookup('cups-print', 'sloc') +
                         _hesiod_lookup('cups-cluster', 'sloc')]
        try:
            cupsd = cups.Connection()
        except RuntimeError:
            pass

        _loaded = True


def get_cups_uri(printer):
    _setup()
    if cupsd:
        try:
            attrs = cupsd.getPrinterAttributes(printer)
            return attrs.get('device-uri')
        except cups.IPPError:
            pass


def find_queue(queue):
    """Figure out which printing system to use for a given printer

    This function makes a best effort to figure out which server and
    which printing system should be used for printing to queue.

    If the specified queue exists on the default CUPS server, then we
    always use CUPS.

    Otherwise, we fall back on Hesiod. If the server in Hesiod accepts
    connections on port 631, we assume CUPS. Otherwise, we assume
    LPRng.

    Note that because a local CUPS queue may point to a remote queue
    of a different name, find_queue includes the name of the queue to
    use against the "remote" print server.

    Args:
      queue: The name of a print queue

    Returns:
      A tuple of (printing_system, print_server, queue_name)

      printing_system is one of the PRINT_* constants in this module
    """
    _setup()
    url = get_cups_uri(queue)
    if url:
        proto = rest = hostport = path = host = port = None

        (proto, rest) = urllib.splittype(url)
        if rest:
            (hostport, path) = urllib.splithost(rest)
        if hostport:
            (host, port) = urllib.splitport(hostport)
        if (proto and host and path and
            proto == 'ipp' and
            host.lower() in CUPS_FRONTENDS + CUPS_BACKENDS):
            # Canonicalize the queue name to Athena's, in case someone
            # has a local printer called something memorable like 'w20'
            # that points to 'ajax' or something
            if path[0:10] == '/printers/':
                queue = path[10:]
            elif path[0:9] == '/classes/':
                queue = path[9:]
            else: # we can't parse CUPS' URL, punt to CUPS
                return SYSTEM_CUPS, None, queue
        else:
            return SYSTEM_CUPS, None, queue

    # Get rid of any instance on the queue name
    # TODO The purpose of instances is to have different sets of default
    # options. Queues may also have default options on the null
    # instance. Figure out if we need to do anything about them
    queue = queue.split('/')[0]

    # If we're still here, the queue is definitely an Athena print
    # queue; it was either in the local cupsd pointing to Athena, or the
    # local cupsd didn't know about it.
    # Figure out what Athena thinks the backend server is, and whether
    # that server is running a cupsd; if not, fall back to LPRng

    pcap = _hesiod_lookup(queue, 'pcap')
    rm = None
    if pcap:
        for field in pcap[0].split(':'):
            if field[0:3] == 'rm=':
                rm = field[3:]
    if not rm:
        # In the unlikely event we're wrong about it being an Athena
        # print queue, the local cupsd is good enough
        return SYSTEM_CUPS, None, queue

    try:
        # See if rm is running a cupsd. If not, assume it's an LPRng server.
        s = socket.socket()
        s.settimeout(0.3)
        s.connect((rm, 631))
        s.close()
    except (socket.error, socket.timeout):
        return SYSTEM_LPRNG, rm, queue

    return SYSTEM_CUPS, rm, queue


__all__ = ['SYSTEM_CUPS', 'SYSTEM_LPRNG',
           'get_cups_uri',
           'find_queue',
           ]