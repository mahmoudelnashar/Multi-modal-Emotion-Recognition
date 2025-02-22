import sys
import os
import threading
from datetime import datetime
from PyQt5.QtCore import QThread,Qt, pyqtSignal as Signal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import *
from PyQt5 import uic
from questions_ui import QuestionsUI
from QuestionsGenerator import *
from llm import PsychologicalReportGenerator
import markdown2
from xhtml2pdf import pisa
import io
import numpy as np
from STT import SpeechToTextProcessor
import pickle
affect = {
    "0": "neutral",
    "1": "happy",
    "2": "sad",
    "3": "surprise",
    "4": "fear",
    "5": "disgust",
    "6": "anger"
}

pages = {
    "homepage": 0,
    "analysis": 1,
    "questions": 2,
    "loading": 3
}

session = None

# class EmotionsThread(QThread):
#     finished = Signal(dict)
#     def get_emotions(self):
#         return predict('2024-06-23_02-04-32')

#     def run(self):

#         emotions = self.get_emotions()
#         self.finished.emit(emotions)

class AnswersThread(QThread):
    finished = Signal(dict)

    def get_answers(self):
        global session
        stt = SpeechToTextProcessor()
        return stt.transcribe_all(session)
        
    def run(self):

        answers = self.get_answers()
        self.finished.emit(answers)

class QuestionsThread(QThread):
    finished = Signal(dict)
   
    def get_questions(self):
        
        # Open and read the JSON file
        with open('questions.json', 'r') as file:
            json_data = file.read()

        # Parse the JSON data into a Python dictionary
        original_response = json.loads(json_data)

        Questions = []
        for key, value in original_response.items():
            Questions.append(value["Question"])

        nquestions = {}
        for i, (key, value) in enumerate(original_response.items(), start=1):
            nquestions[str(i-1)] = value["Question"]
        return nquestions


    def run(self):

        questions = self.get_questions()
        self.finished.emit(questions)

class MainApp(QMainWindow):

    processing_signal = Signal(bool, str)  # Signal with an additional parameter for the message
    update_label_signal = Signal(str)

    def __init__(self):
        super(MainApp, self).__init__()
        self.generate_questions_thread = None
        uic.loadUi("firstScreen.ui", self)

        font = QFont()
        font.setFamily(u"Franklin Gothic Medium")
        font.setPointSize(14)
        font.setBold(True)
        font.setItalic(False)
        font.setUnderline(False)
        font.setWeight(75)
        font.setKerning(True)

        self.loadingScreen = QWidget()

        self.loading_grid_layout = QGridLayout(self.loadingScreen)
        self.vlayout = QVBoxLayout()

        self.loading_label = QLabel()
        self.loading_label.setAlignment(Qt.AlignLeading | Qt.AlignCenter)
        self.loading_label.setFont(font)
        self.loading_label.setStyleSheet(u"color: rgb(255, 255, 255)")
        self.loading_label.setTextFormat(Qt.RichText)
        self.loading_label.setMargin(25)

        self.vlayout.addWidget(self.loading_label)
        self.loading_grid_layout.addLayout(self.vlayout, 0, 0, 1, 1)

        self.stackedPages = self.findChild(QStackedWidget, "stackedWidget")
        self.start_btn = self.findChild(QPushButton, "pushButton_2")
        self.disorder_input = self.findChild(QLineEdit, "lineEdit_2")
        self.new_test_btn = self.findChild(QPushButton, "newTest_btn")
        self.back_final_btn = self.findChild(QPushButton, "backbtn")
        self.save_btn = self.findChild(QPushButton, "savebtn")

        self.new_test_btn.clicked.connect(self.go_to_home)
        self.save_btn.clicked.connect(self.save_as_pdf)
        self.back_final_btn.clicked.connect(self.go_to_question)

        self.disorder_input.setTextMargins(2, 2, 2, 2)

        self.start_btn.clicked.connect(self.generate_questions)
        self.questionScreen = QuestionsUI()
        self.stackedPages.addWidget(self.questionScreen)
        self.stackedPages.addWidget(self.loadingScreen)

        self.processing_signal.connect(self.go_to_loading)
        self.update_label_signal.connect(self.update_analysis_label)

        self.finish_btn_question = self.questionScreen.finish_btn
        self.home_btn_question = self.questionScreen.home_btn

        self.finish_btn_question.clicked.connect(self.go_to_analysis)
        self.home_btn_question.clicked.connect(self.go_to_home)

        self.session_dir = self.create_session_directory()
        
        
        self.log_file_path = os.path.join(self.session_dir, "session_log.txt")

        self.emots = {}
        self.answers = {}
        self.questions = {}
        self.show()

    def create_session_directory(self):
        session_dir = "session"
        if not os.path.exists(session_dir):
            os.mkdir(session_dir)
        
        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        global session
        session = current_time
        session_subdir = os.path.join(session_dir, current_time)
        os.mkdir(session_subdir)
        global session
        session = session_subdir
        return session_subdir

    def load_data(self,pickle_file_path):
        if not os.path.exists(pickle_file_path):
            raise FileNotFoundError(f"No data found for { pickle_file_path}")

        with open(pickle_file_path, 'rb') as f:
            data = pickle.load(f)

        return data

    def get_emotions(self):
        #self.emots_thread = EmotionsThread()
        #self.emots_thread.finished.connect(self.handle_emotions_result)
        #self.emots_thread.start()
        emotions = {}
        #directory = self.get_latest_session_directory()
        directory = self.get_latest_session_directory()
        for filename in os.listdir(directory):
            if filename.endswith('.pkl'):
                q, _ = os.path.splitext(filename) 
                pickle_file_path = os.path.join(directory, f'{ q}.pkl')
                emotions[q] = ''
                data = self.load_data(pickle_file_path)
                exp_average = data['exp_average']
                interp = {affect[str(i)]: round(float(exp_average[i]) * 100, 2) for i in range(len(affect))}
                for emotion, confidence in interp.items():
                    emotions[q] = emotions[q] + f"Emotion: {emotion} Confidence: {confidence}%" + ' , '
                max_emotion = np.argmax(exp_average)
                emotions[q] = affect[str(max_emotion)]
        self.emots = emotions




    def handle_emotions_result(self, emotions):
        self.emots = emotions

    def get_answers(self):
        self.answers_thread = AnswersThread()
        self.answers_thread.finished.connect(self.handle_answers_result)
        self.answers_thread.start()

    def handle_answers_result(self, answers):
        self.answers = answers

    def get_questions(self):
        self.questions_thread = QuestionsThread()
        self.questions_thread.finished.connect(self.handle_questions_result)
        self.questions_thread.start()

    def handle_questions_result(self, questions):
        self.questions = questions


    def log_event(self, message):
        with open(self.log_file_path, "a") as log_file:
            log_file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")

    def get_latest_session_directory(self):
        session_dir = "session"
        if not os.path.exists(session_dir):
            return None
        
        subdirs = [os.path.join(session_dir, d) for d in os.listdir(session_dir) if os.path.isdir(os.path.join(session_dir, d))]
        if not subdirs:
            return None
        
        latest_subdir = max(subdirs, key=os.path.getmtime)
        return latest_subdir

    def generate_questions(self):
        self.generate_questions_thread = QuestionGeneratorThread()
        if self.disorder_input.text() == "":
            msg = QMessageBox()
            msg.setText("Disorder input field cannot be empty!!")
            msg.exec_()
            self.log_event("Disorder input field was empty.")
            return
        input_validator = PsychologicalReportGenerator()
        if input_validator.validate_input(self.disorder_input.text()):
            self.generate_questions_thread.set_topic(self.disorder_input.text())
            self.processing_signal.emit(True, "Generating questions...")  # Emit signal with custom message
            self.generate_questions_thread.start()
            self.generate_questions_thread.finished.connect(self.go_to_question)
            self.log_event("Started generating questions for disorder: " + self.disorder_input.text())
        else:
            msg = QMessageBox()
            msg.setText("This is not a valid Disease/Disorder")
            msg.exec_()
            self.log_event("Invalid Disease/Disorder entered: " + self.disorder_input.text())
            return

    def perform_analysis(self):
        pass

    def go_to_question(self):
        self.questionScreen.question_ui_requested_signal.emit(True)
        self.stackedPages.setCurrentIndex(pages["questions"])
        self.log_event("Navigated to question page.")

    def go_to_loading(self, status, message):
        self.loading_label.setText(message)  # Update loading message
        self.stackedPages.setCurrentIndex(pages["loading"])
        self.log_event("Navigated to loading page with message: " + message)

    def go_to_home(self):
        self.session_dir = self.create_session_directory()
        self.log_file_path = os.path.join(self.session_dir, "session_log.txt")
        self.stackedPages.setCurrentIndex(pages["homepage"])
        self.log_event("Navigated to home page.")

   
    # def get_emotions(self):
    #     # Create instances of the threads
    #     self.emots_thread = EmotionsThread()
    #     self.emots_thread.finished.connect(self.handle_emotions_result)
    #     self.emots_thread.start()

    def get_answers(self):
        self.answers_thread = AnswersThread()
        self.answers_thread.finished.connect(self.handle_answers_result)
        self.answers_thread.start()

    def get_questions(self):
        self.questions_thread = QuestionsThread()

        # Connect the finished signals of each thread to their respective handler methods
        
        self.questions_thread.finished.connect(self.handle_questions_result)

        # Start the threads
        
        
        self.questions_thread.start()




    def go_to_analysis(self):
        # Emit the processing signal
        self.processing_signal.emit(True, "Generating report...")

        threads = []

        # Create a new thread for get_results method
        self.get_emotions()
        print(self.emots)

        thread = threading.Thread(target=self.get_answers)
        threads.append(thread)

        thread = threading.Thread(target=self.get_questions)
        threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()
        
        
       

        while not all([self.answers_thread.isFinished(), self.questions_thread.isFinished()]):
            QApplication.processEvents()  

        # Log the event
        self.log_event("Started processing data.")
        threading.Thread(target=self.load_analysis_report).start()
        self.log_event("Started generating analysis report.")

    def load_analysis_report(self):
        report_generator = PsychologicalReportGenerator()
        # JSON string
        json_string = """
        {
            "Question1": {
                "Question": "Describe a situation where you felt completely overwhelmed, and how did you cope with it?",
                "Answer": "During my final year of college, I had multiple projects and exams piling up, and I felt completely overwhelmed. I took a step back, prioritized my tasks, and delegated some of the workload to my teammates. I also made sure to take breaks and practice self-care to avoid burnout.",
                "Emotion": "Calm"
            },
            "Question2": {
                "Question": "What is the most spontaneous thing you have ever done, and would you do it again?",
                "Answer": "I once decided to take a road trip with friends to a nearby city on a whim. It was amazing, and I would love to do it again. The freedom and excitement of not planning anything and just going with the flow was exhilarating.",
                "Emotion": "Happy"
            },
            "Question3": {
                "Question": "Think of a person you admire, what qualities do they possess that you wish you had, and how can you work on developing those qualities?",
                "Answer": "I admire my grandmother's kindness and empathy towards others. I wish I had her ability to connect with people on a deeper level. I can work on developing this quality by actively listening to others and being more present in my interactions.",
                "Emotion": "Sad"
            }
        }
        """
        
        # Parse the JSON string
        data = json.loads(json_string)
        # Update the emotions using the sorted dictionary
        for i, key in enumerate(self.questions):
            question_key = f"Question{i+1}"
            if question_key in data:
                data[question_key]["Question"] = self.questions[key]
               
            if key in self.emots:
                data[question_key]["Emotion"] = self.emots[key]

            if key in self.answers:
                data[question_key]["Answer"] = self.answers[key]


        # Convert the updated JSON back to a string
        updated_json_string = json.dumps(data, indent=4)

        # Generate the markdown text (assuming report_generator is defined)
        markdown_text = report_generator.generate_report(updated_json_string)


        # Convert Markdown to HTML
        html_content = markdown2.markdown(markdown_text)
        
        # Emit the signal to update the QLabel with the HTML content
        self.update_label_signal.emit(html_content)
        self.log_event("Analysis report generated.")

    def update_analysis_label(self, html_content):
        analysis_label = self.findChild(QLabel, "Analysis_Label")
        analysis_label.setText(html_content)
        self.stackedPages.setCurrentIndex(pages["analysis"])
        self.log_event("Navigated to analysis page.")

    def save_as_pdf(self):
        analysis_label = self.findChild(QLabel, "Analysis_Label")
        html_content = analysis_label.text()
        # Get the latest session directory
        latest_session_dir = self.get_latest_session_directory()
        if not latest_session_dir:
            QMessageBox.critical(self, "Error", "<font color='white'>No session directory found</font>")
            self.log_event("Failed to save PDF: No session directory found")
            return

        output_pdf_path = os.path.join(latest_session_dir, "analysis_report.pdf")
        try:
            with open(output_pdf_path, "wb") as f:
                pisa.CreatePDF(io.StringIO(html_content), dest=f)
            QMessageBox.information(self, "Success", f"<font color='white'>Report saved as {output_pdf_path}</font>")
            self.log_event(f"Report saved as {output_pdf_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"<font color='white'>Failed to save PDF: {str(e)}</font>")
            self.log_event(f"Failed to save PDF: {str(e)}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainApp()
    app.exec_()
