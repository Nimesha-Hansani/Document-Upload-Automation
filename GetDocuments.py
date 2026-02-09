import ctypes
from ctypes import (
    c_uint32, c_char, c_char_p, c_void_p, c_short,
    create_string_buffer, byref
)
import os
from datetime import datetime
import pandas as pd
from DoclLogging import AppLogger
from ExportResults import UpdateStatus


DOWNLOAD_LOG = AppLogger('download_app.log')
# -------------------------------------------------
# Important: Check C:\\Vectus4\\VECTUS.ini - Worked Server/DB: PDCSQL01V & XClaim_lds
# -------------------------------------------------

# os.chdir(r"C:\\Vectus4")  # ***the real install folder



# # -------------------------------------------------
# # Configure these for your environment
# # -------------------------------------------------
DLL_PATH = r"C:\\Vectus4\\Pwm4n.dll"
USER_CODE = b"CHR"
PASSWORD = b"Charlie123"
CASE_ID = 750008216  # <-- ident_dt of the case
BLOB_ID = 751394643  # <-- ident_dt of the blob/document
OUTPUT_DIR = r"C:\\temp"  # target folder



# -------------------------------------------------
# Type aliases (per Vectus C API data types)
# -------------------------------------------------
session_dt = c_uint32  # session handle
ident_dt = c_uint32  # IDs (case, blob, etc.)
size_dt = c_uint32  # sizes
rtn_dt = c_short  # return code (16-bit int)
bool_dt = c_char  # 0/1

# Return codes (subset)
RTN_OK = 0
RTN_OKWITHINFO = 1
BUFFERTOOSMALL = -6


# -------------------------------------------------
# Load the DLL - try CDLL first, switch to WinDLL if needed
# -------------------------------------------------
dll = ctypes.CDLL(DLL_PATH)
# If you observe calling convention issues:
# dll = ctypes.WinDLL(DLL_PATH)

# -------------------------------------------------
# Declare prototypes
# -------------------------------------------------
dll.PWM_LIBRARYINIT.argtypes = []
dll.PWM_LIBRARYINIT.restype = rtn_dt

dll.PWM_LIBRARYQUIT.argtypes = []
dll.PWM_LIBRARYQUIT.restype = rtn_dt

dll.PWM_CONNECT.argtypes = [ctypes.POINTER(session_dt)]
dll.PWM_CONNECT.restype = rtn_dt

dll.PWM_DISCONNECT.argtypes = [session_dt]
dll.PWM_DISCONNECT.restype = rtn_dt

# Logon(session, usercode, password, buffer, buffersize)
dll.PWM_LOGON.argtypes = [session_dt, c_char_p, c_char_p, c_void_p, ctypes.POINTER(size_dt)]
dll.PWM_LOGON.restype = rtn_dt

dll.PWM_LOGOFF.argtypes = [session_dt, c_char_p]
dll.PWM_LOGOFF.restype = rtn_dt

dll.PWM_OPENCASE.argtypes = [session_dt, ident_dt]
dll.PWM_OPENCASE.restype = rtn_dt

# GetDocument(sessionid, caseid, blobid, fileName, docHistInstID,
#             fileExtension, returnBuffer, returnBufferSize)
dll.PWM_GETDOCUMENT.argtypes = [
    session_dt,  # sessionid
    ident_dt,  # caseid
    ident_dt,  # blobid
    c_char_p,  # fileName ("" or NULL -> return in buffer)
    ctypes.POINTER(ident_dt),  # docHistInstID (out)
    c_void_p,  # fileExtension (writable char buffer)
    c_void_p,  # returnBuffer
    ctypes.POINTER(size_dt)  # returnBufferSize (in/out)
]
dll.PWM_GETDOCUMENT.restype = rtn_dt

# Helpful for diagnostics
dll.PWM_LASTMESSAGE.argtypes = [session_dt, c_void_p, size_dt]
dll.PWM_LASTMESSAGE.restype = rtn_dt



def last_message(session):
    buf = create_string_buffer(1024)
    dll.PWM_LASTMESSAGE(session, buf, size_dt(len(buf)))
    return buf.value.decode(errors="ignore")


def require_ok(rc, context, session):
    if rc == RTN_OK:
        print(f"[INFO] {context} returned RTN_OK.")
        return
    elif rc == RTN_OKWITHINFO:
        print(f"[INFO] {context} returned OKWITHINFO.")
        return
    else:
        raise RuntimeError(f"{context} failed rc={rc}; last={last_message(session)}")
    


def get_document_to_bytes(session, case_id: int, blob_id: int):
    """
    Two-call pattern:
      1) size query: pass NULL/empty fileName and NULL buffer, get required size in returnBufferSize
      2) allocate buffer of exact size, fetch bytes
    Returns (bytes_data, extension_str, docHistInstID)
    """


    DOWNLOAD_LOG.info(f"Attempting to fetch document: CaseID={case_id}, BlobID={blob_id}")


    # Dependency: OpenCase
    rc = dll.PWM_OPENCASE(session, ident_dt(case_id))
    require_ok(rc, "OpenCase", session)

    file_name = c_char_p(b"")  # empty -> return bytes (not direct file write)
    doc_hist_inst_id = ident_dt(0)
    ext_buf = create_string_buffer(64)  # enough for typical extensions (e.g., "pdf", "docx", etc.)
    size_out = size_dt(0)

    # First call: ask for size
    buf = (ctypes.c_ubyte * size_out.value)()

    DOWNLOAD_LOG.info(f"Probing size for BlobID {blob_id}")
    rc = dll.PWM_GETDOCUMENT(
        session,
        ident_dt(case_id),
        ident_dt(blob_id),
        file_name,
        byref(doc_hist_inst_id),
        ext_buf,  # writable
        buf,  # returnBuffer -> NULL
        byref(size_out)
    )



    if rc != BUFFERTOOSMALL or size_out.value == 0:
        # Some deployments may return OK with size already set (rare). Handle generically:
        require_ok(rc, "GetDocument(size-query)", session)

        if size_out.value == 0:
            
            DOWNLOAD_LOG.error(f"GetDocument returned no size; check {blob_id} or permissions")
            raise RuntimeError("GetDocument returned no size; check blob id or permissions.")


    # Second call: allocate exact buffer & fetch
    buf = (ctypes.c_ubyte * size_out.value)()
    rc = dll.PWM_GETDOCUMENT(
        session,
        ident_dt(case_id),
        ident_dt(blob_id),
        file_name,
        byref(doc_hist_inst_id),
        ext_buf,
        buf,
        byref(size_out)
    )
    require_ok(rc, "GetDocument(fetch)", session)

    data = bytes(buf)[:size_out.value]
    ext = (ext_buf.value or b"bin").decode(errors="ignore")

    DOWNLOAD_LOG.info(f"GetDocument: Successfully retrieved")
    return data, ext, doc_hist_inst_id.value


def save_bytes(data: bytes, out_dir: str, case_id: int, blob_id: int, ext: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"case_{case_id}_blob_{blob_id}{ext or 'bin'}")

    try :
        with open(out_path, "wb") as f:
            f.write(data)

        DOWNLOAD_LOG.info(f"Successfully saved {len(data)} bytes to: {out_path} (Case: {case_id}, Blob: {blob_id})")

    except Exception as e:

        DOWNLOAD_LOG.error(f"Error on  saving document {blob_id} to {out_path}: {str(e)}")

    return out_path



def main():

    rc = dll.PWM_LIBRARYINIT()
    if rc != RTN_OK:
        raise RuntimeError(f"LibraryInit rc={rc}")


    now = datetime.now()
    DOWNLOAD_LOG.info("Job Started")
    

    session = session_dt(0)
    
    DOCUMENTS_DF = pd.read_csv('SampleDBOutput.csv')
    results_buffer = []  # To store row data + status

    

    for row in DOCUMENTS_DF.itertuples(index=True):

        # Convert row to dictionary to preserve all original columns
        row_data = row._asdict()

 
        CASE_ID = row.CASEID
        BLOB_ID = row.BLOB_ID
        
        # session = session_dt(0)
        DOWNLOAD_LOG.info("Session Initiated")

        try:


            rc = dll.PWM_CONNECT(byref(session))
            require_ok(rc, "Connect", session)


            # Logon (capture any info message in buffer)
            msg_buf = create_string_buffer(512)
            msg_size = size_dt(len(msg_buf))
            rc = dll.PWM_LOGON(session, USER_CODE, PASSWORD, msg_buf, byref(msg_size))
            require_ok(rc, "Logon", session)
            print("Session ID:", session.value)

            DOWNLOAD_LOG.info("Session Logon")


            # Fetch & save
            data, ext, doc_hist_inst_id = get_document_to_bytes(session, CASE_ID, BLOB_ID)
            out_path = save_bytes(data, OUTPUT_DIR, CASE_ID, BLOB_ID, ext)


            # Logoff & Disconnect
            dll.PWM_LOGOFF(session, USER_CODE)
            dll.PWM_DISCONNECT(session)

            DOWNLOAD_LOG.info("Session Disconnected")
            DOWNLOAD_LOG.info(f"Job end time: {datetime.now()}")
            DOWNLOAD_LOG.info(f"Elapsed time: {datetime.now() - now}")

            row_data['STATUS'] = 'SUCCESS'
            

        except Exception as e:

            DOWNLOAD_LOG.error(f"Failed to process document CaseID={CASE_ID}, BlobID={BLOB_ID}: {str(e)}")
            row_data['STATUS'] = 'FAILED'

        finally:
            dll.PWM_LIBRARYQUIT()
            DOWNLOAD_LOG.info("Library resources released successfully (PWM_LIBRARYQUIT).")
        

        # Append the updated row to our buffer
        results_buffer.append(row_data)
                              
    # 2. Final Export
    if results_buffer:

        DOC_STATUS_FOLDER = os.getcwd()
        UpdateStatus().export_results(results_buffer, DOC_STATUS_FOLDER)



if __name__ == "__main__":
    main()