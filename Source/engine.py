import tcod
from entity import get_blocking_entities_at_location
from fov_functions import initialize_fov, recompute_fov
from game_states import GameStates
from input_handlers import handle_keys, handle_mouse, handle_main_menu
from loader_functions.initialize_new_game import get_constants, get_game_variables
from loader_functions.data_loaders import load_game, save_game
from render_functions import render_all
from death_functions import kill_player, kill_monster
from game_messages import Message
from menus import message_box
from debug_functions import print_tile_coord_at_mouse, print_event
import constants as const
from UI_functions import render_main_menu


def play_game(player, entities, game_map, message_log, game_state, con, panel, overlay, constants, context):
    fov_recompute = True
    fov_map = initialize_fov(game_map)

    key = None
    key_event = tcod.event.KeyboardEvent(0, 0, 0)
    mouse = tcod.event.MouseButtonEvent()
    current_mouse_tile = 0, 0
    previous_game_state = game_state

    targeting_item = None

    action = {}

    loop_count = 0

    # Render and present the initial game state:
    recompute_fov(fov_map, player.x, player.y, const.fov_radius, const.fov_light_walls, const.fov_algorithm)
    render_all(con, panel, overlay, entities, player, game_map, fov_map, fov_recompute, message_log, current_mouse_tile,
               const.colors, game_state)
    context.present(con)
    con.clear()

    # Game Loop:
    while True:  # <- Don't love this
        loop_count += 1

        for event in tcod.event.get():
            context.convert_event(event)
            print_event(event)
            if event.type == "KEYDOWN":
                key = event.sym
                key_event = event
            elif event.type == "MOUSEBUTTONDOWN":
                mouse = event
            elif event.type == "MOUSEMOTION":
                mouse = event
                current_mouse_tile = event.tile
                print_tile_coord_at_mouse(event.tile)  # Debug function

        if fov_recompute:
            recompute_fov(fov_map, player.x, player.y, const.fov_radius, const.fov_light_walls, const.fov_algorithm)

        render_all(con, panel, overlay, entities, player, game_map, fov_map, fov_recompute, message_log,
                   current_mouse_tile, const.colors, game_state)
        # fov_recompute = False

        # Console update:
        context.present(con)
        con.clear()

        # clear_all(con, entities)  # Is this effectively replaced by con.clear()?

        # Input Handlers:

        action = handle_keys(key_event, game_state)
        mouse_action = handle_mouse(mouse)
        # The following lines clear the current events. Need a more elegant solution.
        key_event = tcod.event.KeyboardEvent(0, 0, 0)
        key = None
        mouse = tcod.event.MouseButtonEvent()
        # Input results:
        move = action.get('move')
        wait = action.get('wait')
        pickup = action.get('pickup')
        show_inventory = action.get('show_inventory')
        drop_inventory = action.get('drop_inventory')
        inventory_index = action.get('inventory_index')
        take_stairs = action.get('take_stairs')
        level_up = action.get('level_up')
        show_character_screen = action.get('show_character_screen')
        exit = action.get('exit')
        fullscreen = action.get('fullscreen')

        left_click = mouse_action.get('left_click')
        right_click = mouse_action.get('right_click')

        player_turn_results = []

        # Logic:
        if move and game_state == GameStates.PLAYERS_TURN:
            dx, dy = move
            destination_x = player.x + dx
            destination_y = player.y + dy

            if not game_map.is_blocked(destination_x, destination_y):
                target = get_blocking_entities_at_location(entities, destination_x, destination_y)
                if target:
                    attack_results = player.fighter.attack(target)
                    player_turn_results.extend(attack_results)
                else:
                    player.move(dx, dy)
                    fov_recompute = True

                game_state = GameStates.ENEMY_TURN

        elif wait:
            game_state = GameStates.ENEMY_TURN

        elif pickup and game_state == GameStates.PLAYERS_TURN:
            for entity in entities:
                if entity.item and entity.x == player.x and entity.y == player.y:
                    pickup_results = player.inventory.add_item(entity)
                    player_turn_results.extend(pickup_results)

                    break

            else:
                message_log.add_message(Message('There is nothing here to pick up.', tcod.yellow))

        if show_inventory:
            previous_game_state = game_state
            game_state = GameStates.SHOW_INVENTORY

        if drop_inventory:
            previous_game_state = game_state
            game_state = GameStates.DROP_INVENTORY

        if inventory_index is not None and previous_game_state != GameStates.PLAYER_DEAD and inventory_index < len(
                player.inventory.items):
            item = player.inventory.items[inventory_index]

            if game_state == GameStates.SHOW_INVENTORY:
                player_turn_results.extend(player.inventory.use(item, entities=entities, fov_map=fov_map))
            elif game_state == GameStates.DROP_INVENTORY:
                player_turn_results.extend(player.inventory.drop_item(item))

        if take_stairs and game_state == GameStates.PLAYERS_TURN:
            for entity in entities:
                if entity.stairs and entity.x == player.x and entity.y == player.y:
                    entities = game_map.next_floor(player, message_log, constants)
                    fov_map = initialize_fov(game_map)
                    fov_recompute = True
                    tcod.console_clear(con)

                    break
            else:
                message_log.add_message(Message('There are no stairs here.', tcod.yellow))

        if level_up:
            if level_up == 'hp':
                player.fighter.base_max_hp += 20
                player.fighter.hp += 20
            elif level_up == 'str':
                player.fighter.base_power += 1
            elif level_up == 'def':
                player.fighter.base_defense += 1

            game_state = previous_game_state

        if show_character_screen:
            previous_game_state = game_state
            game_state = GameStates.CHARACTER_SCREEN

        if game_state == GameStates.TARGETING:
            if left_click:
                target_x, target_y = left_click

                item_use_results = player.inventory.use(targeting_item, entities=entities, fov_map=fov_map,
                                                        target_x=target_x, target_y=target_y)
                player_turn_results.extend(item_use_results)
            elif right_click:
                player_turn_results.append({'targeting_cancelled': True})

        if exit:
            if game_state in (GameStates.SHOW_INVENTORY, GameStates.DROP_INVENTORY, GameStates.CHARACTER_SCREEN):
                game_state = previous_game_state
            elif game_state == GameStates.TARGETING:
                player_turn_results.append({'targeting_cancelled': True})
            else:
                save_game(player, entities, game_map, message_log, game_state)

                return True

        if fullscreen:  # TODO: This does not work with contexts. Need to find a new way to toggle fullscreen.
            tcod.console_set_fullscreen(not tcod.console_is_fullscreen())

        for player_turn_result in player_turn_results:
            message = player_turn_result.get('message')
            dead_entity = player_turn_result.get('dead')
            item_added = player_turn_result.get('item_added')
            item_consumed = player_turn_result.get('consumed')
            item_dropped = player_turn_result.get('item_dropped')
            equip = player_turn_result.get('equip')
            targeting = player_turn_result.get('targeting')
            targeting_cancelled = player_turn_result.get('targeting_cancelled')
            xp = player_turn_result.get('xp')

            if message:
                message_log.add_message(message)

            if targeting_cancelled:
                game_state = previous_game_state

                message_log.add_message(Message('Targeting cancelled'))

            if xp:
                leveled_up = player.level.add_xp(xp)
                message_log.add_message(Message('You gain {0} experience points.'.format(xp)))

                if leveled_up:
                    message_log.add_message(Message(
                        'Your battle skills grow stronger! You reached level {0}'.format(
                            player.level.current_level) + '!', tcod.yellow))
                    previous_game_state = game_state
                    game_state = GameStates.LEVEL_UP

            if dead_entity:
                if dead_entity == player:
                    message, game_state = kill_player(dead_entity)
                else:
                    message = kill_monster(dead_entity)

                message_log.add_message(message)

            if item_added:
                entities.remove(item_added)

                game_state = GameStates.ENEMY_TURN

            if item_consumed:
                game_state = GameStates.ENEMY_TURN

            if targeting:
                previous_game_state = GameStates.PLAYERS_TURN
                game_state = GameStates.TARGETING

                targeting_item = targeting

                message_log.add_message(targeting_item.item.targeting_message)

            if item_dropped:
                entities.append(item_dropped)

                game_state = GameStates.ENEMY_TURN

            if equip:
                equip_results = player.equipment.toggle_equip(equip)

                for equip_result in equip_results:
                    equipped = equip_result.get('equipped')
                    dequipped = equip_result.get('dequipped')

                    if equipped:
                        message_log.add_message(Message('You equipped the {0}'.format(equipped.name)))

                    if dequipped:
                        message_log.add_message(Message('You dequipped the {0}'.format(dequipped.name)))

                game_state = GameStates.ENEMY_TURN

        if game_state == GameStates.ENEMY_TURN:
            for entity in entities:
                if entity.ai:
                    enemy_turn_results = entity.ai.take_turn(player, fov_map, game_map, entities)

                    for enemy_turn_result in enemy_turn_results:
                        message = enemy_turn_result.get('message')
                        dead_entity = enemy_turn_result.get('dead')

                        if message:
                            message_log.add_message(message)

                        if dead_entity:
                            if dead_entity == player:
                                message, game_state = kill_player(dead_entity)
                            else:
                                message = kill_monster(dead_entity)

                            if message:
                                message_log.add_message(message)
                            # print(message)

                            if game_state == GameStates.PLAYER_DEAD:
                                break
                    if game_state == GameStates.PLAYER_DEAD:
                        break
            else:
                game_state = GameStates.PLAYERS_TURN


def main() -> None:
    constants = get_constants()

    # Load font as a tileset:
    tileset = tcod.tileset.load_tilesheet('assets/arial10x10.png', 32, 8, tcod.tileset.CHARMAP_TCOD)

    player = None
    entities = []
    game_map = None
    message_log = None
    game_state = None

    show_main_menu = True
    show_load_error_message = False

    action = {}

    # main_menu_background_image = tcod.image_load('Assets/menu_background.png')  # Define image object
    main_menu_background_image = tcod.image.load('Assets/menu_background.png')  # Does not currently work

    key = None
    key_event = tcod.event.KeyboardEvent(0, 0, 0)
    mouse = tcod.event.MouseButtonEvent()

    main_loop_count = 0

    # Create a new terminal:
    with tcod.context.new_terminal(
            const.screen_width,
            const.screen_height,
            tileset=tileset,
            title=constants['window_title'],
            vsync=True
    ) as context:
        # Create the root console:
        root_console = tcod.Console(const.screen_width, const.screen_height, order='F')
        # Create console for panel:
        panel = tcod.Console(const.panel_width, const.panel_height, order='F')
        overlay_con = tcod.Console(const.overlay_width, const.overlay_height, order='F')

        while True:  # <- I don't love
            main_loop_count += 1  # For debugging
            for event in tcod.event.wait():
                context.convert_event(event)
                if event.type == "KEYDOWN":
                    key = event.sym
                    key_event = event
                if event.type == "MOUSEMOTION":
                    print_tile_coord_at_mouse(event.tile)  # Debug function
                # elif event.type == "MOUSEBUTTONDOWN":
                #     mouse = event
                mouse = event

            if show_main_menu:
                # Create main menu; pass image object and set height and width to that of the screen.
                # main_menu(root_console, main_menu_background_image, constants['screen_width'],
                #           constants['screen_height'])
                render_main_menu(root_console)

                if show_load_error_message:
                    message_box(root_console, 'No save game to load', 65, const.screen_width,
                                const.screen_height)

                # Update the terminal with the contents of the root console:
                context.present(root_console)
                # Clear the root console:
                root_console.clear()

                # Input Handlers:

                action = handle_main_menu(key_event)
                # The following lines clear the current events. Need a more elegant solution.
                key_event = tcod.event.KeyboardEvent(0, 0, 0)
                key = None

                # Input results
                new_game = action.get('new_game')
                load_saved_game = action.get('load_game')
                exit_game = action.get('exit')

                # Logic:
                if show_load_error_message and (new_game or load_saved_game or exit_game):
                    show_load_error_message = False

                elif new_game:
                    player, entities, game_map, message_log, game_state = get_game_variables(constants)
                    game_state = GameStates.PLAYERS_TURN

                    show_main_menu = False
                elif load_saved_game:
                    try:
                        player, entities, game_map, message_log, game_state = load_game()
                        show_main_menu = False
                    except FileNotFoundError:
                        show_load_error_message = True
                elif exit_game:
                    break

            else:
                root_console.clear()
                play_game(player, entities, game_map, message_log, game_state, root_console, panel, overlay_con,
                          constants, context)

                show_main_menu = True


if __name__ == '__main__':
    main()

