class ChargingStationFSM:
    def __init__(self):
        self.state = 'Available'  # 초기 상태 설정

    # 39P 참고
    transition_table = {
        'Available': {
            'A2': 'Preparing',  # A2: Usage is initiated (e.g., plug inserted, idTag presented)
            'A6': 'Finishing',  # A6: Timed out due to no idTag within timeout
        },
        'Preparing': {
            'B3': 'Charging',  # B3: All prerequisites for charging met, charging starts
            'B1': 'Available',  # B1: Intended usage ended (e.g., plug removed)
            'B6': 'Finishing',  # B6: Timed out due to lack of authorization
        },
        'Charging': {
            'C1': 'Available',  # C1: Charging session ends without user action
            'C6': 'Finishing',  # C6: Transaction stopped by user or remote stop message
        },
        'Finishing': {
            'F1': 'Available',  # F1: All user actions completed, session ends
            'F2': 'Preparing',  # F2: User restarts charging session, creating new transaction
        },
    }

    def on_available(self):
        print("State: Available. Ready for new session.")

    def on_preparing(self):
        print("State: Preparing. Awaiting user action.")

    def on_charging(self):
        print("State: Charging. Power is being delivered to the EV.")

    def on_finishing(self):
        print("State: Finishing. Charging session ending.")

    # 상태에 따른 메서드 매핑
    state_actions = {
        'Available': on_available,
        'Preparing': on_preparing,
        'Charging': on_charging,
        'Finishing': on_finishing,
    }

    # 이벤트를 처리하여 상태 전환
    def handle_event(self, event):
        if event in self.transition_table[self.state]:
            new_state = self.transition_table[self.state][event]
            print(f"Transitioning from {self.state} to {new_state} due to event '{event}'")
            self.state = new_state
            # Call the action associated with the new state
            action = self.state_actions.get(new_state)
            if action:
                action(self)  # Call the bound method without needing `self` as an argument
        else:
            print(f"Invalid event '{event}' for state '{self.state}'")
