#Hier werden schon Mal die wichtigsten Libs, die wir verwenden werden, importiert.
#Geht sicher, dass ihr die installiert habt
import pandas as pd
import streamlit as st
import numpy as np
import json
import torch
import plotly.express as px
import math
import os
import tsfresh
import zipfile as zf
from stqdm import stqdm

st.set_page_config(page_title="Mobility Classification App", page_icon=":oncoming_automobile:", layout="wide")
### Attributes
local = False
if not local:
    knn = torch.load(r"KNN")
    rnf = torch.load(r"RNF")


#Rene Workaround
if local:
    knn = torch.load(r"C:\Users\ReneJ\Desktop\UnityStuff\ML4B-2023\Project\Models\KNN (hpo)_2023-06-02")
    rnf = torch.load(r"C:\Users\ReneJ\Desktop\UnityStuff\ML4B-2023\Project\Models\RNF_2023-06-02")

#Don't touch this! The List has to be identical to the list in the notebook
sensors = ["Accelerometer","Location","Orientation"]

### Functions
def process_data(upload):
    data = None
    if zf.is_zipfile(upload): #Hochgeladene Datei ist eine zip mit CSVs drinnen
        st.write("Is ne zip")
        file = None
        if local:
            extr_dir = r"C:\Users\ReneJ\Desktop\UnityStuff\ML4B-2023\Project\uploaded_files"
        if not local:
            extr_dir = r"uploaded_files"

        with zf.ZipFile(upload, 'r') as zip_ref:
            zip_ref.extractall(extr_dir)

        for f in os.listdir(extr_dir):
            file = f

        data, gps = transform_data_csv(extr_dir + "\\" + file)
        st.write(extr_dir + "\\" + file)

    else: #Hochgeladene Datei ist eine JSON
        st.write("Is ne json")
        x = upload.getvalue()
        #st.write(x)
        x_json = x.decode('utf8')
        data = json.loads(x_json)
        #st.write(s)

        if local:
            json_path = r"C:\Users\ReneJ\Desktop\UnityStuff\ML4B-2023\Project\json.json"
        if not local:
            json_path = r"json.json"

        with open(json_path, 'w') as j:
            json.dump(data,j)
        data, gps = transform_data_json(json_path)

    #st.write(data)
    splitData = split_data([data], 1)
    metrics = calculate_features(splitData)
    end = combine(metrics)

    prediction = rnf.predict(end)

    timeLineData = create_time_line_data(prediction)
    tupelList = time_line_data_to_tupel(timeLineData)
    return tupelList, gps, end, prediction

def transform_data_csv(file):
    datasets = {}  # Ein Dictionary
    gps = None
    for sensor in sensors:
        # Dataframe wird eingelesen
        df = pd.read_csv(file + "\\" + sensor + ".csv")

        # Zeittransformation
        # df["time"] = pd.to_datetime(df['time'], unit = 'ns')
        # df["Readable_Time"] = df["time"]
        # for i in range(0,len(df["time"])):
        #    df["Readable_Time"][i] = df["time"][i].to_pydatetime()
        df = df.drop(columns=["time"])
        df = df.dropna(axis=1)

        # Datenschutz. Falls Location ein Sensor ist, wird davon nur die Speed verwendet
        if (sensor == "Location"):
            gps = df
            df = df.drop(columns=df.columns.difference(["speed", "Readable_Time", "seconds_elapsed"]))

        elif sensor == "Accelerometer":
            df["Magnitude(acc)"] = np.sqrt(df["x"] ** 2 + df["y"] ** 2 + df["z"] ** 2)
            df = df.drop(columns=df.columns.difference(["Magnitude(acc)", "Readable_Time", "seconds_elapsed"]))
        # df["activity"] = action #Darf hier nicht gesetzt werden, ist aber im Dicitonary vermerkt
        df["ID"] = file

        # Dataframe wird dem Dictionay hinzugefügt
        datasets[sensor] = df

    return datasets, gps


def transform_data_json(file):
    datasets = {}  # Ein Dictionary
    gps = None

    df = pd.read_json(file)

    df = df.drop(columns=["time"])

    for sensor in sensors:
        temp = df.loc[df["sensor"] == sensor]
        temp = temp.dropna(axis=1)
        temp = temp.drop(columns=["sensor"])
        # Datenschutz. Falls Location ein Sensor ist, wird davon nur die Speed verwendet
        if (sensor == "Location"):
            gps = temp
            temp = temp.drop(columns=temp.columns.difference(["speed", "Readable_Time", "seconds_elapsed"]))

        elif sensor == "Accelerometer":
            temp["Magnitude(acc)"] = np.sqrt(temp["x"] ** 2 + temp["y"] ** 2 + temp["z"] ** 2)
            temp = temp.drop(columns=temp.columns.difference(["Magnitude(acc)", "Readable_Time", "seconds_elapsed"]))

        # temp["activity"] = action #Darf hier nicht gesetzt werden, ist aber im Dicitonary vermerkt
        temp["ID"] = file

        # Dataframe wird dem Dictionary hinzugefügt
        datasets[sensor] = temp

    return datasets, gps

def split_data(list, length_of_time_series):
    splitted_list = []
    for dict in list:
        amount_of_splits = 999999999999
        print(dict["Accelerometer"].iloc[-1]["ID"])
        # print(dict)
        for sensor in sensors:
            temp_aos = math.floor(dict[sensor]["seconds_elapsed"].iloc[-1] / (60 * length_of_time_series))
            if temp_aos < amount_of_splits:
                amount_of_splits = temp_aos
        print(amount_of_splits)
        if amount_of_splits == 999999999999 or amount_of_splits <= 1:  # case 1: Something went wrong, we don't split. Case 2: The Timeseries is not long enough to be splited
            # Wenn der Datensatz zu kurz zum splitten ist, wird er nicht gesplittet, stattdessen wird er einfach als ganzes in die splitted_list gelegt
            splitted_list.append(dict)

        else:
            split_dict = {}  # Dieses dictionary wird jedem Sensor eine Liste von aufgesplitteten DFs zuweisen
            for sensor in sensors:
                splitted_dict_entry = np.array_split(dict[sensor],
                                                     amount_of_splits)  # Das ist jetzt ne Liste mit aufgeteilten Dataframes
                print(len(splitted_dict_entry))
                id_suffix = 0
                for df in splitted_dict_entry:
                    df["ID"] = df["ID"] + "_" + str(id_suffix)
                    id_suffix += 1

                split_dict[sensor] = splitted_dict_entry

            for i in range(0, amount_of_splits):
                sub_dict = {}
                for sensor in sensors:
                    sub_dict[sensor] = split_dict[sensor][i]
                splitted_list.append(sub_dict)

    return splitted_list


def calculate_features(input_list):
    ff_list = []

    def rms(df):
        square = df ** 2
        square = square.sum()
        mean = (square / len(df))
        root = math.sqrt(mean)
        return root


    for dict in stqdm(input_list):
        #print((list(dict.keys())[1] == "Accelerometer") and (list(dict.keys())[2] == "Location") and (
        #            list(dict.keys())[3] == "Orientation"))

        for sensor in sensors:

            dict[sensor] = dict[sensor].drop(columns=["seconds_elapsed"])

            if sensor == "Accelerometer" or sensor == "Location":
                temp = tsfresh.extract_features(dict[sensor], column_id="ID",
                                                default_fc_parameters=tsfresh.feature_extraction.MinimalFCParameters(),
                                                n_jobs=4)

                if sensor == "Location":  # Orientation Stuff. I don't get it better merged, tbh
                    temp["roll__standard_deviation"] = dict["Orientation"]["roll"].std()
                    temp["roll__variance"] = dict["Orientation"]["roll"].var()
                    temp["roll__root_mean_square"] = rms(dict["Orientation"]["roll"])

                    temp["pitch__standard_deviation"] = dict["Orientation"]["pitch"].std()
                    temp["pitch__variance"] = dict["Orientation"]["pitch"].var()
                    temp["pitch__root_mean_square"] = rms(dict["Orientation"]["pitch"])
                    temp["pitch__absolute_maximum"] = dict["Orientation"]["pitch"].abs().max()

                    temp["yaw__standard_deviation"] = dict["Orientation"]["yaw"].std()
                    temp["yaw__variance"] = dict["Orientation"]["yaw"].var()

                ff_list.append({"data": temp.copy(), "sensor": sensor})


            elif sensor == "Gravity":
                temp["Magnitude(grav)__sum_values"] = dict[sensor]["Magnitude(grav)"].sum()
                temp["Magnitude(grav)__mean"] = dict[sensor]["Magnitude(grav)"].mean()
                temp["Magnitude(grav)__minimum"] = dict[sensor]["Magnitude(grav)"].min()

            elif sensor == "Orientation":
                continue

    return ff_list

def combine(final_form_data_list):
    very_final_form_data_list = []

    for sensor in sensors:
        if sensor == "Orientation":
            continue
        temp_list = []
        for dict in final_form_data_list:
            if str(dict["sensor"]) == str(sensor):
                temp_list.append(dict["data"])
        concat_temp = pd.concat(temp_list)
        very_final_form_data_list.append(concat_temp)


    #Join all the Dataframes to one Dataframe
    df_final = pd.concat(very_final_form_data_list, axis = 1)

    #Drop duplicate "activity" Columns
    d = df_final.T.drop_duplicates().T
    df_final = df_final.drop(columns=["activity"])

    df_final["activity"] = d["activity"]

    #Final Dataframe with all the transformed data
    return df_final


class activityCountMapper:
    activity: str
    count: int

    def __init__(self, act: str):  # Konstruktor der Klasse
        self.activity = act
        self.count = 1

    def countUp(self):
        self.count += 1

    def getActivity(self) -> str:
        return self.activity

    def getCount(self) -> int:
        return self.count

def create_time_line_data(dataList:list):
    returnList = []
    global latestElement
    latestElement = None

    for entry in dataList:
        if latestElement == None:
            latestElement = str(entry)
            returnList.append(activityCountMapper(str(entry)))
        elif str(entry) == latestElement:
            returnList[len(returnList) -1].countUp()
        elif str(entry) != latestElement:
            returnList.append(activityCountMapper(str(entry)))

    return returnList

def time_line_data_to_tupel(time_line):
    tupel_list = []
    for entry in time_line:
        tupel_list.append((entry.getActivity(),entry.getCount()))

    return tupel_list

### Pythonic Area

### Streamlit Area

st.subheader("Lets classify your mobility!")
st.write("First we need some Input from you")
#uploaded_file = st.file_uploader("Please upload a sensor data file. JSON or .zip containing CSVs are allowed")
#knn = torch.load(r"..\Models" + "\\" + "KNN (hpo)_2023-06-02")
def main():
    uploaded_file = st.file_uploader("Please upload a sensor data file. JSON or .zip containing CSVs are allowed", accept_multiple_files=False)
    if st.button("Classify me!"):
        prediction_data, gps, metric_data, raw_predictions = process_data(uploaded_file)
        st.header("prediction_data")
        st.write(prediction_data)
        st.header("gps")
        st.write(gps)
        st.header("metric_data")
        st.write(metric_data)
        st.header("raw_predictions")
        st.write(raw_predictions)
        st.subheader("Der Ursprung deiner Daten")
        st.write("Keine Sorge, nur du kannst diese Daten sehen, wir haben nicht genug Geld für Streamlit Pro, daher können wir die nicht speichern ;D")
        st.map(gps)
        st.subheader("Dein Fortbewegungsgraph")
        output_string = ""
        import graphviz
        graph = graphviz.Digraph()
        i = 0
        if len(prediction_data) > 1:
            while i < len(prediction_data) -1:
                graph.edge((prediction_data[i][0] + " " + str(prediction_data[i][1]) + " min"), (prediction_data[i+1][0] + " " + str(prediction_data[i+1][1]) + " min"))
                i += 1
        else:
            graph.edge(prediction_data[i][0] + " " + str(prediction_data[i][1]) + " min", "End")
        st.write(output_string)
        st.graphviz_chart(graph)

        st.subheader("Deine Fortbewegungsverteilung")
        
if __name__ == "__main__":
    main()



