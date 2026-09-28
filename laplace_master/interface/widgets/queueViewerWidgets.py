# libraries

from laplace_log import log
from .abstractQueueViewerWidget import AbstractQueueViewerWidget


class OptQueueViewerWidget(AbstractQueueViewerWidget):
    '''
    Widget used to display and navigate optimization queue elements.

    Displays:
        - Current element index / total
        - Inputs (grouped by IP)
        - Outputs (grouped by IP and keys)

    Provides:
        - Navigate left/right
        - Delete current element
    '''

    def __init__(self):
        super().__init__()

    def set_queue(self, suggestions: list, obj_spec: dict) -> None:
        '''Replace the queue with a new list of suggestions.'''
        # set the queue
        self.queue = [dict(s, outputs=obj_spec) for s in suggestions] # attach outputs to each suggestion
        self.current_index = 0
        log.info(f'self.queue in OptQueueViewer: {self.queue}')
        # update the widget
        self.update_display()
        self.update_buttons()

    def update_display(self) -> None:
        '''Update the text display for the current suggestion.'''
        if not self.queue:                                  # if there is no element in the queue
            self.text_display.setText("<empty queue>")      # print it
            self.label_index.setText("0 / 0")               # adapt the counter
            return
        
        item = self.queue[self.current_index]                   # else get the current element in the queue
        text_lines = ["<b>Inputs:</b>"]
        for ip, positions in item.get("inputs", {}).items():
            text_lines.append(f"{ip}: {positions}")             # make one line per input ip

        text_lines.append("<b>Outputs:</b>")
        for ip, keys in item.get("outputs", {}).items():
            text_lines.append(f"{ip}: {list(keys)}")            # make one line per objective ip

        self.text_display.setHtml("<br>".join(text_lines))                          # update the displayed text
        self.label_index.setText(f"{self.current_index + 1} / {len(self.queue)}")   # update the index counter label 

class ScanQueueViewerWidget(AbstractQueueViewerWidget):
    '''
    Widget used to display and navigate scan queue elements.

    Displays:
        - Current element index / total
        - Inputs (grouped by IP)

    Provides:
        - Navigate left/right
        - Delete current element
    '''

    def __init__(self):
        super().__init__()

    def set_queue(self, suggestions: list, obj_spec: dict) -> None:
        '''Replace the queue with a new list of suggestions.'''
        # set the queue

        self.queue = [dict(s) for s in suggestions] # attach outputs to each suggestion
        self.current_index = 0
        
        # update the widget
        self.update_display()
        self.update_buttons()


    def update_display(self) -> None:
        '''Update the text display for the current suggestion.'''
        if not self.queue:                                  # if there is no element in the queue
            self.text_display.setText("<empty queue>")      # print it
            self.label_index.setText("0 / 0")               # adapt the counter
            return
        
        item = self.queue[self.current_index]                   # else get the current element in the queue
        log.info(f'Item: {item}')
        text_lines = ["<b>Inputs:</b>"]
        for ip, positions in item.items():
            text_lines.append(f"{ip}: {positions}")             # make one line per input ip

            log.info(f'IP: {ip}, positions: {positions}, current index: {self.current_index}')

        self.text_display.setHtml("<br>".join(text_lines))                          # update the displayed text
        self.label_index.setText(f"{self.current_index + 1} / {len(self.queue)}")   # update the index counter label 
