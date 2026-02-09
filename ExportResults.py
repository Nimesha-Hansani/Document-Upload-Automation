import os 
import pandas as pd
from datetime import datetime
from DoclLogging import AppLogger

class UpdateStatus:

    
    
     def export_results(self,RESULT_LIST, OUTPUT_DIR):

     
        results_df = pd.DataFrame(RESULT_LIST)
        report_path = os.path.join(OUTPUT_DIR, f"Processing_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        print(report_path)
        results_df.to_csv(report_path, index=False)
        


